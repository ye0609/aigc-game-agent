"""Train a frozen ImageNet ResNet18 head, export ONNX, and evaluate grouped holdout."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18

from classifier import file_sha256, write_metrics
from dataset import load_group_manifest, validate_dataset
from onnx_model import OnnxClassifier, MEAN, STD, open_rgb, preprocess
from train import split_by_group


SEED = 20261018


def extract_features(backbone, files: list[Path], *, augment: bool) -> torch.Tensor:
    pipeline = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.65, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15),
        transforms.ToTensor(),
        transforms.Normalize(MEAN.tolist(), STD.tolist()),
    ])
    output = []
    with torch.inference_mode():
        for start in range(0, len(files), 16):
            batch = []
            for path in files[start:start + 16]:
                image_bytes = path.read_bytes()
                if augment:
                    batch.append(pipeline(open_rgb(image_bytes)))
                else:
                    batch.append(torch.from_numpy(preprocess(image_bytes)[0]))
            output.append(backbone(torch.stack(batch)))
    return torch.cat(output)


def train(root: Path, catalog: Path, output: Path, min_per_class: int = 30) -> dict:
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    random.seed(SEED)
    torch.set_num_threads(min(8, max(1, torch.get_num_threads())))
    report = validate_dataset(root, catalog, min_per_class)
    if not report["ready"]:
        raise ValueError(f"训练集未就绪：{report['missing']}")
    groups_path = root / "groups.csv"
    group_by_path = load_group_manifest(root, report["files"], groups_path)
    training, validation, train_groups, validation_groups = split_by_group(report["files"], group_by_path)
    labels = list(report["counts"])
    train_files = [path for label in labels for path in training[label]]
    train_targets = torch.tensor([index for index, label in enumerate(labels) for _ in training[label]], dtype=torch.long)
    val_files = [path for label in labels for path in validation[label]]
    val_targets = [index for index, label in enumerate(labels) for _ in validation[label]]

    model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.eval()
    model.fc = torch.nn.Identity()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    print(f"提取训练特征：{len(train_files)} 张，3 个视图", flush=True)
    features = [extract_features(model, train_files, augment=False)]
    for _ in range(2):
        features.append(extract_features(model, train_files, augment=True))
    features = torch.cat(features)
    targets = train_targets.repeat(3)

    head = torch.nn.Linear(512, len(labels))
    optimizer = torch.optim.AdamW(head.parameters(), lr=0.003, weight_decay=0.1)
    head.train()
    for _ in range(150):
        optimizer.zero_grad()
        loss = torch.nn.functional.cross_entropy(head(features), targets, label_smoothing=0.1)
        loss.backward()
        optimizer.step()
    head.eval()
    model.fc = head
    model.eval()

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.onnx")
    try:
        torch.onnx.export(
            model, torch.zeros((1, 3, 224, 224)), str(temporary),
            input_names=["image"], output_names=["logits"],
            opset_version=17, dynamo=False,
        )
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    deployed = OnnxClassifier(output, labels)
    correct = 0
    per_class = {label: Counter() for label in labels}
    max_logit_difference = 0.0
    with torch.inference_mode():
        for path, expected in zip(val_files, val_targets):
            image_bytes = path.read_bytes()
            tensor = torch.from_numpy(preprocess(image_bytes))
            pytorch_logits = model(tensor).numpy()[0]
            onnx_logits = deployed.logits(image_bytes)
            max_logit_difference = max(max_logit_difference, float(np.max(np.abs(pytorch_logits - onnx_logits))))
            predicted = int(np.argmax(onnx_logits))
            correct += predicted == expected
            per_class[labels[expected]][labels[predicted]] += 1
    if max_logit_difference > 1e-3:
        raise ValueError(f"PyTorch 与 ONNX 输出不一致：最大 logit 差 {max_logit_difference:.6f}")
    accuracy = correct / len(val_files)
    metrics = {
        "model": "resnet18-onnx-v1",
        "pretrainedWeights": "ResNet18_Weights.IMAGENET1K_V1",
        "classes": labels,
        "trainSamples": len(train_files),
        "validationSamples": len(val_files),
        "validationSplit": "grouped-by-group_id",
        "trainGroups": train_groups,
        "validationGroups": validation_groups,
        "validationCorrect": correct,
        "validationAccuracy": round(accuracy, 4),
        "validationConfusion": {label: dict(counts) for label, counts in per_class.items()},
        "onnxMaxLogitDifference": round(max_logit_difference, 7),
        "seed": SEED,
        "groupsSha256": file_sha256(groups_path),
        "sourcesSha256": file_sha256(root / "sources.csv") if (root / "sources.csv").exists() else None,
        "readyForDemo": accuracy >= 0.75,
        "modelSha256": file_sha256(output),
    }
    write_metrics(output.with_name("metrics.json"), metrics)
    return metrics


def main():
    parser = argparse.ArgumentParser(description="训练四类红树 ResNet18 并导出 ONNX")
    parser.add_argument("--root", type=Path, default=Path("data/recognition"))
    parser.add_argument("--catalog", type=Path, default=Path("data/species.catalog.json"))
    parser.add_argument("--output", type=Path, default=Path("backend/recognition/artifacts/model.onnx"))
    parser.add_argument("--min-per-class", type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(train(args.root, args.catalog, args.output, args.min_per_class), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
