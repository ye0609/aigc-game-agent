"""训练红树识别基线并输出模型和评估结果。"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from classifier import CentroidClassifier, image_feature, write_metrics
from dataset import load_group_manifest, validate_dataset


def split_by_group(files_by_class: dict[str, list[Path]], group_by_path: dict[Path, str], validation_fraction: float = 0.2, seed: int = 20261018):
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction 必须介于 0 和 1 之间")
    rng = random.Random(seed)
    training: dict[str, list[Path]] = {}
    validation: dict[str, list[Path]] = {}
    training_groups: dict[str, int] = {}
    validation_groups: dict[str, int] = {}

    for label, files in sorted(files_by_class.items()):
        grouped: dict[str, list[Path]] = {}
        for path in files:
            group_id = group_by_path.get(path)
            if not group_id:
                raise ValueError(f"图片缺少采集组：{path}")
            grouped.setdefault(group_id, []).append(path)
        if len(grouped) < 2:
            raise ValueError(f"类别 {label} 只有 {len(grouped)} 个采集组；至少需要 2 个，才能隔离验证集")

        group_ids = list(grouped)
        rng.shuffle(group_ids)
        target = len(files) * validation_fraction
        selected = [min(group_ids, key=lambda group_id: abs(len(grouped[group_id]) - target))]
        while len(selected) < len(group_ids) - 1:
            selected_count = sum(len(grouped[group_id]) for group_id in selected)
            current_error = abs(target - selected_count)
            candidates = [group_id for group_id in group_ids if group_id not in selected]
            candidate = min(
                candidates,
                key=lambda group_id: abs(target - selected_count - len(grouped[group_id])),
            )
            next_error = abs(target - selected_count - len(grouped[candidate]))
            if next_error >= current_error:
                break
            selected.append(candidate)

        validation_ids = set(selected)
        validation[label] = [path for group_id in selected for path in grouped[group_id]]
        training[label] = [path for group_id, paths in grouped.items() if group_id not in validation_ids for path in paths]
        validation_groups[label] = len(validation_ids)
        training_groups[label] = len(grouped) - len(validation_ids)

    return training, validation, training_groups, validation_groups


def train(root: Path, catalog: Path, output: Path, min_per_class: int, groups_path: Path | None = None):
    report = validate_dataset(root, catalog, min_per_class)
    if not report["ready"]:
        raise SystemExit(f"训练集未就绪，缺少类别：{', '.join(report['missing'])}")
    group_by_path = load_group_manifest(root, report["files"], groups_path)
    train_files, validation_files, train_groups, validation_groups = split_by_group(report["files"], group_by_path)
    train_features = []
    train_labels = []
    validation_features = []
    validation_labels = []
    for label, files in train_files.items():
        for path in files:
            train_features.append(image_feature(path.read_bytes()))
            train_labels.append(label)
    for label, files in validation_files.items():
        for path in files:
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
        "validationSplit": "grouped-by-group_id",
        "trainGroups": train_groups,
        "validationGroups": validation_groups,
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
    parser.add_argument("--groups", type=Path, help="image,group_id 清单；默认读取训练集目录下的 groups.csv")
    parser.add_argument("--min-per-class", type=int, default=30)
    args = parser.parse_args()
    print(train(args.root, args.catalog, args.output, args.min_per_class, args.groups))


if __name__ == "__main__":
    main()
