"""训练红树识别基线并输出模型和评估结果。"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from classifier import CentroidClassifier, image_feature, write_metrics
from dataset import validate_dataset


def train(root: Path, catalog: Path, output: Path, min_per_class: int):
    report = validate_dataset(root, catalog, min_per_class)
    if not report["ready"]:
        raise SystemExit(f"训练集未就绪，缺少类别：{', '.join(report['missing'])}")
    rng = random.Random(20261018)
    train_features = []
    train_labels = []
    validation_features = []
    validation_labels = []
    for label, files in report["files"].items():
        shuffled = list(files)
        rng.shuffle(shuffled)
        split = max(1, int(len(shuffled) * 0.8))
        for path in shuffled[:split]:
            train_features.append(image_feature(path.read_bytes()))
            train_labels.append(label)
        for path in shuffled[split:]:
            validation_features.append(image_feature(path.read_bytes()))
            validation_labels.append(label)
    model = CentroidClassifier.fit(np.vstack(train_features), train_labels, list(report["counts"]))
    correct = 0
    for feature, label in zip(validation_features, validation_labels):
        correct += model.predict(feature)["label"] == label
    validation_total = len(validation_labels)
    metrics = {
        "model": "centroid-rgb-spatial-v1",
        "classes": list(report["counts"]),
        "trainSamples": len(train_labels),
        "validationSamples": validation_total,
        "validationAccuracy": round(correct / validation_total, 4) if validation_total else None,
        "readyForDemo": validation_total > 0 and correct / validation_total >= 0.75,
    }
    model.save(output)
    write_metrics(output.with_name("metrics.json"), metrics)
    return metrics


def main():
    parser = argparse.ArgumentParser(description="训练红树识别基线")
    parser.add_argument("--root", type=Path, default=Path("data/recognition"))
    parser.add_argument("--catalog", type=Path, default=Path("data/species.catalog.json"))
    parser.add_argument("--output", type=Path, default=Path("backend/recognition/artifacts/model.npz"))
    parser.add_argument("--min-per-class", type=int, default=30)
    args = parser.parse_args()
    print(train(args.root, args.catalog, args.output, args.min_per_class))


if __name__ == "__main__":
    main()
