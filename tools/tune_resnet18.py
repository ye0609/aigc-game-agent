"""Compare class balancing and last-layer fine tuning without touching demo artifacts.

The fixed 56-image holdout is evaluated only after a configuration is selected on
an internal grouped development split. Results are written to an experiment folder.
"""

from __future__ import annotations

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
from onnx_model import MEAN, STD, OnnxClassifier, open_rgb, preprocess  # noqa: E402
from classifier import file_sha256  # noqa: E402
import evaluate_china_groups as original_evaluation  # noqa: E402

SEED = 20261021
BASE = ROOT / "data" / "recognition"
CHINA = ROOT / "data" / "recognition-china-curated-20261021"
OUT = ROOT / "data" / "recognition-tuning-20261021"
HOLDOUT_CHINA = {"127075651", "187221888", "194431895", "98685443", "99627936"}


def rows(root: Path) -> list[dict[str, str]]:
    with (root / "sources.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def label(row: dict[str, str]) -> str:
    return row["image"].split("/", 1)[0]


def group(row: dict[str, str]) -> str:
    return f"{label(row)}:{row['photographer_id']}"


def split_groups(entries: list[tuple[Path, dict[str, str]]], *, fraction: float, seed: int) -> tuple[list, list]:
    grouped: dict[str, list] = defaultdict(list)
    for entry in entries:
        grouped[group(entry[1])].append(entry)
    by_label: dict[str, list[str]] = defaultdict(list)
    for group_id in grouped:
        by_label[group_id.split(":", 1)[0]].append(group_id)
    dev_ids: set[str] = set()
    for species, ids in sorted(by_label.items()):
        rng = random.Random(seed)
        rng.shuffle(ids)
        total = sum(len(grouped[g]) for g in ids)
        target = round(total * fraction)
        # Find a combination of whole photographer groups near 20%. A single
        # prolific photographer must not consume most of the development split.
        possible: dict[int, tuple[str, ...]] = {0: ()}
        for group_id in ids:
            count = len(grouped[group_id])
            for current, chosen in list(possible.items()):
                next_count = current + count
                if next_count <= total - 20 and next_count not in possible:
                    possible[next_count] = chosen + (group_id,)
        choices = [count for count in possible if count > 0]
        if not choices:
            raise ValueError(f"no valid development split for {species}")
        best = min(choices, key=lambda count: (abs(count - target), count))
        dev_ids.update(possible[best])
    dev = [entry for entry in entries if group(entry[1]) in dev_ids]
    train = [entry for entry in entries if group(entry[1]) not in dev_ids]
    return train, dev


def fixed_splits() -> tuple[list, list]:
    base, china = rows(BASE), rows(CHINA)
    old_holdout = original_evaluation.old_holdout(base, china)
    old_val = [(BASE, row) for row in base if group(row) in old_holdout]
    china_val = [(CHINA, row) for row in china if row["observation_id"] in HOLDOUT_CHINA]
    if len(old_val) != 31 or len(china_val) != 25:
        raise ValueError(f"locked holdout changed: {len(old_val)} original, {len(china_val)} China")
    holdout_keys = {(root, row["image"]) for root, row in old_val + china_val}
    train = [(BASE, row) for row in base if (BASE, row["image"]) not in holdout_keys]
    train += [(CHINA, row) for row in china if (CHINA, row["image"]) not in holdout_keys]
    return train, old_val + china_val


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


def make_model(finetune: bool) -> torch.nn.Module:
    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = torch.nn.Linear(512, 4)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in model.fc.parameters():
        parameter.requires_grad_(True)
    if finetune:
        for parameter in model.layer4.parameters():
            parameter.requires_grad_(True)
    return model


def path_of(entry: tuple[Path, dict[str, str]]) -> Path:
    return entry[0] / entry[1]["image"]


def train_variant(train_entries: list, dev_entries: list, *, weighted: bool, finetune: bool) -> tuple[torch.nn.Module, dict]:
    labels = sorted({label(row) for _, row in train_entries})
    index = {name: i for i, name in enumerate(labels)}
    counts = Counter(label(row) for _, row in train_entries)
    weights = None
    if weighted:
        weights = torch.tensor([1.0 / counts[name] for name in labels], dtype=torch.float32)
        weights = weights / weights.mean()
    if not finetune:
        # Cache the frozen backbone once. This is the same recipe as the production
        # trainer, but keeps the four configuration comparisons practical on CPU.
        backbone = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        backbone.fc = torch.nn.Identity()
        backbone.eval()
        with torch.no_grad():
            feature_batches = []
            target_batches = []
            for augment in (False, True, True):
                for start in range(0, len(train_entries), 32):
                    batch = train_entries[start:start + 32]
                    feature_batches.append(backbone(torch.stack([tensor(path_of(e), augment) for e in batch])))
                    target_batches.append(torch.tensor([index[label(e[1])] for e in batch], dtype=torch.long))
            features = torch.cat(feature_batches).clone()
            targets = torch.cat(target_batches)
        head = torch.nn.Linear(512, len(labels))
        optimizer = torch.optim.AdamW(head.parameters(), lr=0.003, weight_decay=0.1)
        for _ in range(150):
            optimizer.zero_grad()
            loss = torch.nn.functional.cross_entropy(head(features), targets, weight=weights, label_smoothing=0.1)
            loss.backward()
            optimizer.step()
        model = torch.nn.Sequential(backbone, head).eval()
        return model, evaluate_torch(model, dev_entries, labels)

    model = make_model(True)
    model.eval()
    model.layer4.train()
    model.fc.train()
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=0.0003, weight_decay=0.01)
    rng = random.Random(SEED)
    # A short, conservative fine-tuning run is enough to decide whether layer4
    # helps; longer training is not justified by this small dataset.
    for _ in range(12):
        order = list(range(len(train_entries)))
        rng.shuffle(order)
        for start in range(0, len(order), 32):
            batch_entries = [train_entries[i] for i in order[start:start + 32]]
            images = torch.stack([tensor(path_of(entry), augment=True) for entry in batch_entries])
            targets = torch.tensor([index[label(entry[1])] for entry in batch_entries], dtype=torch.long)
            optimizer.zero_grad()
            logits = model(images)
            loss = torch.nn.functional.cross_entropy(logits, targets, weight=weights, label_smoothing=0.05)
            loss.backward()
            optimizer.step()
    model.eval()
    return model, evaluate_torch(model, dev_entries, labels)


def evaluate_torch(model: torch.nn.Module, entries: list, labels: list[str]) -> dict:
    correct = 0
    confusion = {name: Counter() for name in labels}
    with torch.inference_mode():
        for root, row in entries:
            logits = model(tensor(path_of((root, row)), augment=False).unsqueeze(0))[0]
            predicted = labels[int(torch.argmax(logits))]
            expected = label(row)
            correct += predicted == expected
            confusion[expected][predicted] += 1
    return {"correct": correct, "total": len(entries), "accuracy": round(correct / len(entries), 4),
            "confusion": {key: dict(value) for key, value in confusion.items() if value}}


def main() -> None:
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.set_num_threads(min(8, max(1, torch.get_num_threads())))
    fixed_train, fixed_holdout = fixed_splits()
    train_entries, dev_entries = split_groups(fixed_train, fraction=0.2, seed=SEED + 1)
    results = []
    for weighted, finetune in ((False, False), (True, False), (False, True), (True, True)):
        name = f"{'weighted' if weighted else 'plain'}-{'layer4' if finetune else 'head'}"
        print(f"training {name}: train={len(train_entries)} dev={len(dev_entries)}", flush=True)
        model, dev = train_variant(train_entries, dev_entries, weighted=weighted, finetune=finetune)
        results.append({"variant": name, "weighted": weighted, "finetuneLayer4": finetune,
                        "trainSamples": len(train_entries), "devSamples": len(dev_entries),
                        "dev": dev})
    selected = max(results, key=lambda result: result["dev"]["correct"])
    print(f"selected {selected['variant']}; retraining on {len(fixed_train)} photos", flush=True)
    torch.manual_seed(SEED)
    selected_model, _ = train_variant(fixed_train, dev_entries, weighted=selected["weighted"], finetune=selected["finetuneLayer4"])
    labels = sorted({label(row) for _, row in fixed_train})
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "model.onnx"
    temporary = OUT / "model.tmp.onnx"
    torch.onnx.export(selected_model, torch.zeros((1, 3, 224, 224)), str(temporary),
                      input_names=["image"], output_names=["logits"], opset_version=17, dynamo=False)
    temporary.replace(output)
    deployed = OnnxClassifier(output, labels)
    onnx_correct = 0
    max_difference = 0.0
    with torch.inference_mode():
        for entry in fixed_holdout:
            image_bytes = path_of(entry).read_bytes()
            torch_logits = selected_model(torch.from_numpy(preprocess(image_bytes))).numpy()[0]
            onnx_logits = deployed.logits(image_bytes)
            max_difference = max(max_difference, float(np.max(np.abs(torch_logits - onnx_logits))))
            onnx_correct += labels[int(np.argmax(onnx_logits))] == label(entry[1])
    if max_difference > 1e-3:
        raise ValueError(f"PyTorch/ONNX mismatch: {max_difference}")
    final = evaluate_torch(selected_model, fixed_holdout, labels)
    if final["correct"] != onnx_correct:
        raise ValueError("PyTorch/ONNX predictions differ")
    result = {"seed": SEED, "results": results, "selected": selected["variant"],
        "fullTrainSamples": len(fixed_train), "fixedHoldoutResult": final,
        "onnxMaxLogitDifference": max_difference, "modelSha256": file_sha256(output),
        "fixedHoldout": "31 original photographer images + 25 China observation images",
        "readyForDemo": False,
        "warning": "This holdout is not independent Zhanjiang field validation. Earlier exploratory runs exposed the holdout to multiple variants."}
    (OUT / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
