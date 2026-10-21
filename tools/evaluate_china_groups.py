"""Compare baseline and China-group expansion on fixed old and site holdouts.

Both models train with the same frozen ImageNet ResNet18 recipe. China photo
holdout observations come from distinct geotagged sites and are never trained.
This exploratory result is not a field validation or demo-readiness decision.
"""

from __future__ import annotations

import csv
import json
import random
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "recognition"))
import train_resnet18  # noqa: E402
from onnx_model import OnnxClassifier  # noqa: E402


BASE = ROOT / "data" / "recognition"
CHINA = ROOT / "data" / "recognition-china-curated-20261021"
CATALOG = ROOT / "data" / "species.catalog.json"
EXPERIMENT = ROOT / "data" / "recognition-china-experiment-20261021"
HOLDOUT_CHINA_OBSERVATIONS = {
    # Three Kandelia groups northeast of Taipei; no images from these
    # observations enter training.
    "127075651", "187221888", "99627936",
    # Two Avicennia groups around the Qigu coast in Tainan.
    "194431895", "98685443",
}


def rows(root: Path) -> list[dict[str, str]]:
    with (root / "sources.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def species_id(row: dict[str, str]) -> str:
    return row["image"].split("/", 1)[0]


def photographer_group(row: dict[str, str]) -> str:
    return f"{species_id(row)}:{row['photographer_id']}"


def old_holdout(base_rows: list[dict[str, str]], china_rows: list[dict[str, str]]) -> set[str]:
    china_photographers = {photographer_group(row) for row in china_rows}
    by_species: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in base_rows:
        by_species[species_id(row)][photographer_group(row)] += 1
    rng = random.Random(20261021)
    selected = set()
    for species in sorted(by_species):
        groups = sorted(group for group in by_species[species] if group not in china_photographers)
        rng.shuffle(groups)
        target = round(sum(by_species[species].values()) * 0.2)
        count = 0
        for group in groups:
            if count >= target:
                break
            selected.add(group)
            count += by_species[species][group]
    return selected


def materialize(root: Path, entries: list[tuple[Path, dict[str, str]]]) -> None:
    root.mkdir(parents=True)
    result_rows = []
    for source_root, original in entries:
        row = dict(original)
        row["group_id"] = photographer_group(row)
        destination = root / row["image"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / row["image"], destination)
        result_rows.append(row)
    fields = list(result_rows[0])
    for row in result_rows[1:]:
        for field in row:
            if field not in fields:
                fields.append(field)
    with (root / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result_rows)
    with (root / "groups.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
        writer.writeheader()
        writer.writerows({"image": row["image"], "group_id": row["group_id"]} for row in result_rows)


def evaluate(model_path: Path, entries: list[tuple[Path, dict[str, str]]], labels: list[str]) -> dict:
    model = OnnxClassifier(model_path, labels)
    correct = 0
    confusion = {label: Counter() for label in labels}
    for source_root, row in entries:
        predicted = labels[int(np.argmax(model.logits((source_root / row["image"]).read_bytes())))]
        expected = species_id(row)
        correct += predicted == expected
        confusion[expected][predicted] += 1
    return {
        "correct": correct,
        "total": len(entries),
        "accuracy": round(correct / len(entries), 4) if entries else None,
        "confusion": {label: dict(counts) for label, counts in confusion.items() if counts},
    }


def main() -> None:
    base_rows, china_rows = rows(BASE), rows(CHINA)
    base_obs = {row["observation_id"] for row in base_rows}
    if any(row["observation_id"] in base_obs for row in china_rows):
        raise ValueError("China collection contains an original observation")
    if {row["observation_id"] for row in china_rows}.isdisjoint(HOLDOUT_CHINA_OBSERVATIONS):
        raise ValueError("China site holdout is missing")
    val_photographers = old_holdout(base_rows, china_rows)
    old_val = [(BASE, row) for row in base_rows if photographer_group(row) in val_photographers]
    site_val = [(CHINA, row) for row in china_rows if row["observation_id"] in HOLDOUT_CHINA_OBSERVATIONS]
    if len(site_val) < 20:
        raise ValueError("China site holdout is too small")
    work = Path(tempfile.mkdtemp(prefix="aigc-china-group-eval-"))
    base_root, expanded_root = work / "base-data", work / "expanded-data"
    materialize(base_root, [(BASE, row) for row in base_rows])
    materialize(expanded_root, [(BASE, row) for row in base_rows] + [(CHINA, row) for row in china_rows])

    def split(files_by_class, group_by_path):
        training, validation, train_groups, val_groups = {}, {}, {}, {}
        for label, files in files_by_class.items():
            training[label], validation[label] = [], []
            for path in files:
                if path.name.startswith("IMG_"):
                    holdout = group_by_path[path] in val_photographers
                else:
                    holdout = path.stem.split("_", 1)[0] in HOLDOUT_CHINA_OBSERVATIONS
                (validation if holdout else training)[label].append(path)
            if not training[label] or not validation[label]:
                raise ValueError(f"empty split: {label}")
            train_groups[label] = len({group_by_path[path] for path in training[label]})
            val_groups[label] = len({group_by_path[path] for path in validation[label]})
        return training, validation, train_groups, val_groups

    train_resnet18.split_by_group = split
    print("training baseline", flush=True)
    baseline = train_resnet18.train(base_root, CATALOG, work / "baseline" / "model.onnx")
    print("training China-expanded model", flush=True)
    expanded = train_resnet18.train(expanded_root, CATALOG, work / "expanded" / "model.onnx")
    expanded["validationSplit"] = "fixed-original-photographers-plus-China-observation-sites"
    expanded["validationWarning"] = "Some China holdout sites share photographers with training sites; no independent field validation"
    expanded["readyForDemo"] = False
    train_resnet18.write_metrics(work / "expanded" / "metrics.json", expanded)
    labels = baseline["classes"]
    result = {
        "holdout": {
            "originalPhotographers": sorted(val_photographers),
            "chinaObservationIds": sorted(HOLDOUT_CHINA_OBSERVATIONS),
            "originalPhotos": len(old_val),
            "chinaSitePhotos": len(site_val),
        },
        "baseline": {
            "trainSamples": baseline["trainSamples"],
            "original": evaluate(work / "baseline" / "model.onnx", old_val, labels),
            "chinaSites": evaluate(work / "baseline" / "model.onnx", site_val, labels),
        },
        "expanded": {
            "trainSamples": expanded["trainSamples"],
            "original": evaluate(work / "expanded" / "model.onnx", old_val, labels),
            "chinaSites": evaluate(work / "expanded" / "model.onnx", site_val, labels),
        },
        "workDirectory": str(work),
        "readyForDemo": False,
        "readinessReason": "Exploratory geotagged observation holdout is not independent field validation",
    }
    (work / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    EXPERIMENT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(work / "expanded" / "model.onnx", EXPERIMENT / "model.onnx")
    shutil.copy2(work / "expanded" / "metrics.json", EXPERIMENT / "metrics.json")
    publish_result = {key: value for key, value in result.items() if key != "workDirectory"}
    (EXPERIMENT / "comparison.json").write_text(
        json.dumps(publish_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
