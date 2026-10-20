"""Compare licensed photo expansion on one fixed, photographer-disjoint holdout.

This experiment leaves the project's training set and deployed model untouched.
It uses existing photos as a fixed validation set and excludes expansion photos
from those photographers, so both runs are evaluated on identical images.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "recognition"))
import train_resnet18  # noqa: E402


EXCLUDED_OBSERVATIONS = {
    "364570210": "mud photo with no visible plant",
    "213354782": "distant seedlings with too little identifying detail",
    "197943329": "detached propagule without a visible tree",
}
ALLOWED_LICENSES = {"cc0", "cc-by", "cc-by-sa"}
MAX_PER_PHOTOGRAPHER = 7


def read_sources(root: Path) -> list[dict[str, str]]:
    with (root / "sources.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    seen_images: set[str] = set()
    seen_hashes: set[str] = set()
    for row in rows:
        relative = Path(row["image"])
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
            raise ValueError(f"invalid image path: {row['image']}")
        if row["image"] in seen_images or row["sha256"] in seen_hashes:
            raise ValueError(f"duplicate image or hash: {row['image']}")
        seen_images.add(row["image"])
        seen_hashes.add(row["sha256"])
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"missing or modified image: {row['image']}")
    return rows


def photographer_group(row: dict[str, str]) -> str:
    species_id = row["image"].split("/", 1)[0]
    return f"inat-photographer-{species_id}-{row['photographer_id']}"


def choose_holdout(rows: list[dict[str, str]]) -> set[str]:
    by_species: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        species_id = row["image"].split("/", 1)[0]
        by_species[species_id][photographer_group(row)] += 1
    rng = random.Random(20261020)
    selected: set[str] = set()
    for species_id in sorted(by_species):
        groups = sorted(by_species[species_id])
        rng.shuffle(groups)
        target = round(sum(by_species[species_id].values()) * 0.2)
        count = 0
        for group_id in groups:
            if count >= target:
                break
            selected.add(group_id)
            count += by_species[species_id][group_id]
    return selected


def write_dataset(destination: Path, entries: list[tuple[Path, dict[str, str]]]) -> None:
    destination.mkdir(parents=True)
    rows = []
    for source_root, original in entries:
        row = dict(original)
        source = source_root / row["image"]
        target = destination / row["image"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        row["group_id"] = photographer_group(row)
        rows.append(row)
    rows.sort(key=lambda row: row["image"])
    with (destination / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with (destination / "groups.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
        writer.writeheader()
        writer.writerows({"image": row["image"], "group_id": row["group_id"]} for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extra-root", type=Path, action="append", required=True)
    parser.add_argument("--base-root", type=Path, default=ROOT / "data" / "recognition")
    args = parser.parse_args()
    base = args.base_root.resolve()
    extras = [(root.resolve(), read_sources(root.resolve())) for root in args.extra_root]
    old_rows = read_sources(base)
    for row in old_rows + [row for _, rows in extras for row in rows]:
        if row["license"] not in ALLOWED_LICENSES:
            raise ValueError(f"unapproved license: {row['image']}")
    holdout = choose_holdout(old_rows)
    old_hashes = {row["sha256"] for row in old_rows}
    old_observations = {row["observation_id"] for row in old_rows}
    photographer_counts = Counter(photographer_group(row) for row in old_rows)
    image_numbers = Counter()
    for row in old_rows:
        species_id, filename = row["image"].split("/", 1)
        image_numbers[species_id] = max(image_numbers[species_id], int(Path(filename).stem.split("_")[-1]))
    extra_entries: list[tuple[Path, dict[str, str]]] = []
    rejection_counts = Counter()
    for extra, original in [(root, row) for root, rows in extras for row in rows]:
        row = dict(original)
        if row["sha256"] in old_hashes or row["observation_id"] in old_observations:
            rejection_counts["already in base"] += 1
            continue
        if row["observation_id"] in EXCLUDED_OBSERVATIONS:
            rejection_counts["visually uninformative"] += 1
            continue
        group_id = photographer_group(row)
        if group_id in holdout:
            rejection_counts["holdout photographer"] += 1
            continue
        if photographer_counts[group_id] >= MAX_PER_PHOTOGRAPHER:
            rejection_counts["photographer cap"] += 1
            continue
        species_id = row["image"].split("/", 1)[0]
        image_numbers[species_id] += 1
        row["image"] = f"{species_id}/IMG_{image_numbers[species_id]:04d}.jpg"
        # The source filename differs from the merged filename.
        extra_entries.append((extra / original["image"], row))
        photographer_counts[group_id] += 1
        old_hashes.add(row["sha256"])
        old_observations.add(row["observation_id"])

    work = Path(tempfile.mkdtemp(prefix="aigc-recognition-eval-"))
    baseline_root, expanded_root = work / "baseline-data", work / "expanded-data"
    write_dataset(baseline_root, [(base, row) for row in old_rows])
    # Materialize renamed expansion files before using the shared writer.
    staging = work / "renamed-extras"
    for source, row in extra_entries:
        target = staging / row["image"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_dataset(expanded_root, [(base, row) for row in old_rows] + [(staging, row) for _, row in extra_entries])

    def fixed_split(files_by_class, group_by_path):
        training, validation, train_groups, val_groups = {}, {}, {}, {}
        for label, files in files_by_class.items():
            training[label] = [path for path in files if group_by_path[path] not in holdout]
            validation[label] = [path for path in files if group_by_path[path] in holdout]
            if not training[label] or not validation[label]:
                raise ValueError(f"empty training or validation class: {label}")
            train_groups[label] = len({group_by_path[path] for path in training[label]})
            val_groups[label] = len({group_by_path[path] for path in validation[label]})
        return training, validation, train_groups, val_groups

    train_resnet18.split_by_group = fixed_split
    catalog = ROOT / "data" / "species.catalog.json"
    print(f"work directory: {work}", flush=True)
    print(f"new eligible photos: {len(extra_entries)}; exclusions: {dict(rejection_counts)}", flush=True)
    print("training original dataset on fixed photographer holdout", flush=True)
    baseline = train_resnet18.train(baseline_root, catalog, work / "baseline" / "model.onnx")
    print("training expanded dataset on the same holdout", flush=True)
    expanded = train_resnet18.train(expanded_root, catalog, work / "expanded" / "model.onnx")
    summary = {
        "holdout": "fixed photographers, original images only",
        "baseline": {key: baseline[key] for key in ("trainSamples", "validationSamples", "validationCorrect", "validationAccuracy")},
        "expanded": {key: expanded[key] for key in ("trainSamples", "validationSamples", "validationCorrect", "validationAccuracy")},
        "eligibleNewPhotos": len(extra_entries),
        "excluded": dict(rejection_counts),
        "workingDirectory": str(work),
        "visuallyExcludedObservations": EXCLUDED_OBSERVATIONS,
    }
    (work / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
