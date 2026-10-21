"""Evaluate EfficientNet-B0 on the same grouped mangrove photo split.

Outputs a local candidate model and a tracked JSON report. Never changes the
formal backend model. The previously explored fixed holdout is not blind.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0

import tune_resnet18 as common
from classifier import file_sha256
from onnx_model import OnnxClassifier, preprocess

ROOT = common.ROOT
OUT = ROOT / "data" / "recognition-efficientnet-b0-20261021"
SEED = common.SEED


def make_model(finetune_last_block: bool) -> torch.nn.Module:
    model = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
    model.classifier[1] = torch.nn.Linear(model.classifier[1].in_features, 4)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in model.classifier.parameters():
        parameter.requires_grad_(True)
    if finetune_last_block:
        # Unfreeze the last MBConv block and final projection layer.
        for parameter in model.features[-2:].parameters():
            parameter.requires_grad_(True)
    return model


def fit_variant(train_entries, dev_entries, *, weighted: bool, finetune: bool):
    labels = sorted({common.label(row) for _, row in train_entries})
    label_index = {name: i for i, name in enumerate(labels)}
    counts = {name: sum(common.label(row) == name for _, row in train_entries) for name in labels}
    weights = None
    if weighted:
        weights = torch.tensor([1.0 / counts[name] for name in labels], dtype=torch.float32)
        weights /= weights.mean()

    model = make_model(finetune)
    if not finetune:
        model.features.eval()
        model.avgpool.eval()
        with torch.no_grad():
            features, targets = [], []
            for augment in (False, True, True):
                for start in range(0, len(train_entries), 24):
                    batch = train_entries[start:start + 24]
                    images = torch.stack([common.tensor(common.path_of(e), augment) for e in batch])
                    values = model.avgpool(model.features(images)).flatten(1)
                    features.append(values)
                    targets.append(torch.tensor([label_index[common.label(e[1])] for e in batch]))
            features = torch.cat(features).clone()
            targets = torch.cat(targets)
        head = model.classifier
        optimizer = torch.optim.AdamW(head.parameters(), lr=0.003, weight_decay=0.1)
        for _ in range(150):
            optimizer.zero_grad()
            loss = torch.nn.functional.cross_entropy(head(features), targets, weight=weights, label_smoothing=0.1)
            loss.backward()
            optimizer.step()
        model.eval()
    else:
        # Freeze BatchNorm statistics outside the trainable layers. Small data
        # does not support updating all pretrained normalization statistics.
        model.eval()
        model.features[-2].train()
        model.features[-1].train()
        model.classifier.train()
        for module in model.modules():
            if isinstance(module, torch.nn.BatchNorm2d):
                module.eval()
        parameters = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW(parameters, lr=0.0003, weight_decay=0.01)
        rng = random.Random(SEED)
        for _ in range(12):
            order = list(range(len(train_entries)))
            rng.shuffle(order)
            for start in range(0, len(order), 24):
                batch = [train_entries[i] for i in order[start:start + 24]]
                images = torch.stack([common.tensor(common.path_of(e), True) for e in batch])
                targets = torch.tensor([label_index[common.label(e[1])] for e in batch])
                optimizer.zero_grad()
                logits = model(images)
                loss = torch.nn.functional.cross_entropy(logits, targets, weight=weights, label_smoothing=0.05)
                loss.backward()
                optimizer.step()
        model.eval()
    return model, common.evaluate_torch(model, dev_entries, labels)


def benchmark(model_path: Path, entries, labels: list[str]) -> dict:
    classifier = OnnxClassifier(model_path, labels)
    images = [common.path_of(entry).read_bytes() for entry in entries]
    for image in images[:5]:
        classifier.logits(image)
    elapsed = []
    for _ in range(3):
        start = time.perf_counter()
        for image in images:
            classifier.logits(image)
        elapsed.append((time.perf_counter() - start) * 1000 / len(images))
    samples = sorted(elapsed)
    return {"images": len(images), "repeats": len(elapsed),
            "meanMsPerImage": round(float(np.mean(elapsed)), 2),
            "p95RepeatMeanMsPerImage": round(samples[-1], 2),
            "note": "CPU ONNX inference only; excludes upload, preprocessing outside Python, and network latency."}


def main() -> None:
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.set_num_threads(min(8, max(1, torch.get_num_threads())))
    fixed_train, fixed_holdout = common.fixed_splits()
    train_entries, dev_entries = common.split_groups(fixed_train, fraction=0.2, seed=SEED + 1)
    print(f"EfficientNet-B0 weights: {EfficientNet_B0_Weights.IMAGENET1K_V1.url}", flush=True)
    print(f"grouped split: fit={len(train_entries)}, development={len(dev_entries)}, final={len(fixed_holdout)}", flush=True)
    variants = ((False, False), (False, True), (True, True))
    results = []
    for weighted, finetune in variants:
        name = f"{'weighted' if weighted else 'plain'}-{'last-block' if finetune else 'head'}"
        print(f"training {name}", flush=True)
        torch.manual_seed(SEED)
        model, dev = fit_variant(train_entries, dev_entries, weighted=weighted, finetune=finetune)
        results.append({"variant": name, "weighted": weighted, "finetuneLastBlock": finetune,
                        "trainSamples": len(train_entries), "developmentSamples": len(dev_entries), "development": dev})

    # Deterministic tie-break is first listed: simpler head-only fine tuning.
    selected = max(results, key=lambda item: item["development"]["correct"])
    print(f"selected {selected['variant']}; refitting on {len(fixed_train)} images", flush=True)
    torch.manual_seed(SEED)
    selected_model, _ = fit_variant(fixed_train, dev_entries, weighted=selected["weighted"],
                                    finetune=selected["finetuneLastBlock"])
    labels = sorted({common.label(row) for _, row in fixed_train})
    OUT.mkdir(parents=True, exist_ok=True)
    model_path = OUT / "model.onnx"
    temporary = OUT / "model.tmp.onnx"
    torch.onnx.export(selected_model, torch.zeros((1, 3, 224, 224)), str(temporary),
                      input_names=["image"], output_names=["logits"], opset_version=17, dynamo=False)
    temporary.replace(model_path)
    deployed = OnnxClassifier(model_path, labels)
    correct = 0
    max_difference = 0.0
    with torch.inference_mode():
        for entry in fixed_holdout:
            image_bytes = common.path_of(entry).read_bytes()
            reference = selected_model(torch.from_numpy(preprocess(image_bytes))).numpy()[0]
            actual = deployed.logits(image_bytes)
            max_difference = max(max_difference, float(np.max(np.abs(reference - actual))))
            correct += labels[int(np.argmax(actual))] == common.label(entry[1])
    if max_difference > 1e-3:
        raise ValueError(f"PyTorch / ONNX output mismatch: {max_difference}")
    holdout = common.evaluate_torch(selected_model, fixed_holdout, labels)
    if correct != holdout["correct"]:
        raise ValueError("PyTorch and ONNX holdout predictions differ")
    old_model = ROOT / "data" / "recognition-china-experiment-20261021" / "model.onnx"
    report = {
        "date": "2026-10-21", "architecture": "EfficientNet-B0",
        "pretrainedWeights": "EfficientNet_B0_Weights.IMAGENET1K_V1",
        "seed": SEED, "trainingImages": len(fixed_train),
        "developmentSplit": "grouped-by-photographer; no group overlap",
        "developmentResults": results, "selected": selected["variant"],
        "fixedHoldoutResult": holdout,
        "onnxMaxLogitDifference": round(max_difference, 8),
        "modelBytes": model_path.stat().st_size, "modelSha256": file_sha256(model_path),
        "cpuBenchmarkEfficientNet": benchmark(model_path, fixed_holdout, labels),
        "fixedResNetModelExists": old_model.is_file(),
        "readyForDemo": False,
        "warning": "The 56-image holdout was already used in prior model experiments; this is exploratory, not independent Zhanjiang field validation."
    }
    if old_model.is_file():
        report["cpuBenchmarkResNet18"] = benchmark(old_model, fixed_holdout, labels)
        report["resnet18ModelBytes"] = old_model.stat().st_size
    (OUT / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
