"""Train/evaluate a grouped ResNet18 candidate using licensed mangrove photos.

The candidate is saved outside the production backend artifacts directory.
Photographer IDs are kept together across all included sources so the
development split does not share authors with training.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "recognition"))
from classifier import file_sha256  # noqa: E402
from onnx_model import MEAN, STD, OnnxClassifier, open_rgb, preprocess  # noqa: E402

SEED = 20261022
SOURCES = [
    ROOT / "data" / "recognition",
    ROOT / "data" / "recognition-china-curated-20261021",
    ROOT / "data" / "recognition-balance-20261021",
]
OUT = ROOT / "data" / "recognition-balance-20261021"


def load_entries() -> list[tuple[Path, dict[str, str]]]:
    entries = []
    hashes: dict[str, tuple[Path, str]] = {}
    for root in SOURCES:
        manifest = root / ("curated.csv" if root == OUT else "sources.csv")
        with manifest.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if root == OUT and row["image"] in {
                    "mangrove-aegiceras-corniculatum/INAT_0032.jpg",
                    "mangrove-avicennia-marina/INAT_0023.jpg",
                    "mangrove-avicennia-marina/INAT_0024.jpg",
                    "mangrove-kandelia-obovata/INAT_0016.jpg",
                    "mangrove-kandelia-obovata/INAT_0032.jpg",
                    "mangrove-kandelia-obovata/INAT_0034.jpg",
                    "mangrove-kandelia-obovata/INAT_0036.jpg",
                }:
                    raise ValueError(f"excluded image must not be in curated manifest: {row['image']}")
                if row.get("license", "").lower() not in {"cc0", "cc-by", "cc-by-sa"}:
                    raise ValueError(f"unsupported license in training manifest: {row['image']}")
                if not row.get("photographer_id"):
                    raise ValueError(f"missing photographer ID: {row['image']}")
                path = root / row["image"]
                if not path.is_file():
                    raise FileNotFoundError(path)
                digest = file_sha256(path)
                expected = row.get("sha256")
                if expected and digest != expected:
                    raise ValueError(f"SHA-256 mismatch: {path}")
                if digest in hashes:
                    previous, _ = hashes[digest]
                    raise ValueError(f"duplicate photo content: {previous} and {path}")
                hashes[digest] = (path, row["image"])
                row["_root"] = str(root)
                row["_label"] = row["image"].split("/", 1)[0]
                entries.append((path, row))
    return entries


def split_photographers(entries: list[tuple[Path, dict[str, str]]], fraction: float = 0.2):
    by_author: dict[str, list] = defaultdict(list)
    for entry in entries:
        by_author[entry[1]["photographer_id"]].append(entry)
    old_authors = {row["photographer_id"] for _, row in entries
                   if Path(row["_root"]) != OUT}
    candidate_authors = {row["photographer_id"] for _, row in entries
                         if Path(row["_root"]) == OUT and row["photographer_id"] not in old_authors}
    candidate_groups = {author: by_author[author] for author in candidate_authors}
    labels = sorted({row["_label"] for _, row in entries})
    candidate_counts = Counter(row["_label"] for author in candidate_authors
                                for _, row in by_author[author])
    if set(candidate_counts) != set(labels):
        raise ValueError(f"new-batch-only authors do not cover every class: {candidate_counts}")
    target = {label: round(candidate_counts[label] * fraction) for label in labels}
    selected: set[str] = set()
    selected_counts: Counter[str] = Counter()
    # Greedily add complete photographer groups when doing so reduces the
    # total distance to 20% per class. Never leave fewer than 20 train images.
    while True:
        before = sum(abs(target[label] - selected_counts[label]) for label in labels)
        candidates = []
        for author, author_entries in candidate_groups.items():
            if author in selected:
                continue
            increment = Counter(row["_label"] for _, row in author_entries)
            after = sum(abs(target[label] - selected_counts[label] - increment[label]) for label in labels)
            if after < before:
                candidates.append((after, author))
        if not candidates:
            break
        _, author = min(candidates)
        selected.add(author)
        selected_counts.update(row["_label"] for _, row in by_author[author])
    development = [entry for entry in entries if entry[1]["photographer_id"] in selected]
    training = [entry for entry in entries if entry[1]["photographer_id"] not in selected]
    if not development or {row["_label"] for _, row in development} != set(labels):
        raise ValueError("new-batch photographer holdout did not put every class in development")
    if any(author in old_authors for author in selected):
        raise ValueError("development authors overlap with historical source authors")
    return training, development, sorted(selected)


def tensor(path: Path, augment: bool) -> torch.Tensor:
    image = open_rgb(path.read_bytes())
    if augment:
        pipeline = transforms.Compose([
            transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15),
            transforms.ToTensor(), transforms.Normalize(MEAN.tolist(), STD.tolist()),
        ])
        return pipeline(image)
    return torch.from_numpy(preprocess(path.read_bytes())[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=12)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    random.seed(SEED)
    torch.set_num_threads(min(8, max(1, torch.get_num_threads())))

    entries = load_entries()
    labels = sorted({row["_label"] for _, row in entries})
    training, development, dev_authors = split_photographers(entries)
    index = {label: i for i, label in enumerate(labels)}
    train_counts = Counter(row["_label"] for _, row in training)
    dev_counts = Counter(row["_label"] for _, row in development)
    if any(count < 20 for count in train_counts.values()):
        raise ValueError(f"too few training images by class: {train_counts}")

    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = torch.nn.Linear(512, len(labels))
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in model.fc.parameters():
        parameter.requires_grad_(True)
    for parameter in model.layer4.parameters():
        parameter.requires_grad_(True)
    model.eval()
    model.layer4.train()
    model.fc.train()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=0.0003, weight_decay=0.01)
    class_weights = torch.tensor([len(training) / train_counts[label] for label in labels], dtype=torch.float32)
    class_weights /= class_weights.mean()
    rng = random.Random(SEED)
    for epoch in range(args.epochs):
        order = list(range(len(training)))
        rng.shuffle(order)
        losses = []
        for start in range(0, len(order), 24):
            batch = [training[i] for i in order[start:start + 24]]
            images = torch.stack([tensor(path, True) for path, _ in batch])
            targets = torch.tensor([index[row["_label"]] for _, row in batch])
            optimizer.zero_grad()
            logits = model(images)
            loss = torch.nn.functional.cross_entropy(logits, targets, weight=class_weights, label_smoothing=0.05)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))
        print(f"epoch {epoch + 1}/{args.epochs} loss={np.mean(losses):.4f}", flush=True)
    model.eval()

    confusion = {label: Counter() for label in labels}
    correct = 0
    with torch.inference_mode():
        for path, row in development:
            logits = model(tensor(path, False).unsqueeze(0))[0]
            predicted = labels[int(torch.argmax(logits))]
            expected = row["_label"]
            confusion[expected][predicted] += 1
            correct += predicted == expected
    accuracy = correct / len(development)
    OUT.mkdir(parents=True, exist_ok=True)
    model_path = OUT / "resnet18-expanded-candidate.onnx"
    temporary = OUT / "resnet18-expanded-candidate.tmp.onnx"
    torch.onnx.export(model, torch.zeros((1, 3, 224, 224)), str(temporary),
                      input_names=["image"], output_names=["logits"], opset_version=17, dynamo=False)
    temporary.replace(model_path)
    deployed = OnnxClassifier(model_path, labels)
    max_difference = 0.0
    onnx_correct = 0
    with torch.inference_mode():
        for path, row in development:
            image_bytes = path.read_bytes()
            expected = row["_label"]
            reference = model(torch.from_numpy(preprocess(image_bytes))).numpy()[0]
            actual = deployed.logits(image_bytes)
            max_difference = max(max_difference, float(np.max(np.abs(reference - actual))))
            onnx_correct += labels[int(np.argmax(actual))] == expected
    if max_difference > 1e-3 or onnx_correct != correct:
        raise ValueError(f"PyTorch/ONNX mismatch: maxLogitDiff={max_difference}, correct={correct}/{onnx_correct}")

    metrics = {
        "date": "2026-10-21", "architecture": "ResNet18", "weights": "ImageNet1K_V1",
        "classes": labels,
        "seed": SEED, "epochs": args.epochs,
        "sources": [str(path.relative_to(ROOT)).replace("\\", "/") for path in SOURCES],
        "sourceSha256": {str((root / name).relative_to(ROOT)).replace("\\", "/"): file_sha256(root / name)
                         for root, name in [(ROOT / "data" / "recognition", "sources.csv"),
                                            (ROOT / "data" / "recognition-china-curated-20261021", "sources.csv"),
                                            (OUT, "curated.csv")]},
        "trainingSamples": len(training), "developmentSamples": len(development),
        "trainingByClass": dict(train_counts), "developmentByClass": dict(dev_counts),
        "developmentSplit": "new-batch photos only; photographers absent from all historical sources; no author overlap",
        "developmentAuthors": dev_authors,
        "developmentCorrect": correct, "developmentAccuracy": round(accuracy, 4),
        "perClassRecall": {label: round(confusion[label][label] / sum(confusion[label].values()), 4) for label in labels},
        "macroRecall": round(float(np.mean([confusion[label][label] / sum(confusion[label].values()) for label in labels])), 4),
        "confusion": {label: dict(counts) for label, counts in confusion.items()},
        "onnxMaxLogitDifference": round(max_difference, 8),
        "modelBytes": model_path.stat().st_size, "modelSha256": file_sha256(model_path),
        "candidateMeets75PercentDevelopmentGate": accuracy >= 0.75,
        "readyForDemo": False,
        "warning": "This is an online-photo, photographer-held-out development result, not independent Zhanjiang field validation. The production model is not changed by this script.",
    }
    (OUT / "expanded-resnet18-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
