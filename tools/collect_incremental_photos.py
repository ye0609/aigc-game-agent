"""Collect additional licensed iNaturalist photos with resumable manifests.

Existing datasets are used for deduplication. Each accepted image and its
source record are saved immediately, so an interrupted run can be resumed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

from collect_training_images import (
    API_URL,
    ALLOWED_LICENSES,
    SOURCE_FIELDS,
    TARGETS,
    get_bytes,
    get_json,
)


ROOT = Path(__file__).resolve().parents[1]


def licensed_candidates(search_name: str, accepted_name: str):
    query = {
        "taxon_name": search_name,
        "photos": "true",
        "quality_grade": "research",
        "photo_license": "cc0,cc-by,cc-by-sa",
        "per_page": 10,
        "order": "desc",
        "order_by": "observed_on",
    }

    def fetch(page: int) -> dict:
        return get_json(API_URL + "?" + urlencode({**query, "page": page}))

    first = fetch(1)
    page_count = min(30, (int(first["total_results"]) + 9) // 10)
    print(f"{search_name}: {first['total_results']} licensed observations", flush=True)
    for observation in first.get("results", []):
        if (observation.get("taxon") or {}).get("name") == accepted_name:
            for photo in observation.get("photos") or []:
                license_code = str(photo.get("license_code") or "").lower()
                if license_code in ALLOWED_LICENSES and photo.get("url"):
                    yield observation, observation.get("user") or {}, photo, license_code
                    break
    with ThreadPoolExecutor(max_workers=4) as pool:
        for start in range(2, page_count + 1, 4):
            for result in pool.map(fetch, range(start, min(start + 4, page_count + 1))):
                for observation in result.get("results", []):
                    if (observation.get("taxon") or {}).get("name") != accepted_name:
                        continue
                    for photo in observation.get("photos") or []:
                        license_code = str(photo.get("license_code") or "").lower()
                        if license_code in ALLOWED_LICENSES and photo.get("url"):
                            yield observation, observation.get("user") or {}, photo, license_code
                            break


def read_rows(root: Path) -> list[dict[str, str]]:
    source = root / "sources.csv"
    if not source.exists():
        return []
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        path = root / row["image"]
        if row["license"] not in ALLOWED_LICENSES or not path.is_file():
            raise ValueError(f"Invalid source row: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Image hash mismatch: {path}")
    return rows


def save_rows(root: Path, rows: list[dict[str, str]]) -> None:
    for name, fields, values in (
        ("sources.csv", SOURCE_FIELDS, rows),
        ("groups.csv", ["image", "group_id"], rows),
    ):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=root,
            prefix=f".{name}.", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(sorted(values, key=lambda row: row["image"]))
        os.replace(temporary, root / name)


def collect(root: Path, existing_roots: list[Path], species_ids: list[str], target: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = read_rows(root)
    known = rows + [row for existing in existing_roots for row in read_rows(existing)]
    hashes = {row["sha256"] for row in known}
    observations = {row["observation_id"] for row in known}
    photo_ids = {row["photo_id"] for row in known}
    for species_id in species_ids:
        search_name, accepted_name, _ = TARGETS[species_id]
        directory = root / species_id
        directory.mkdir(exist_ok=True)
        current = [row for row in rows if row["image"].startswith(f"{species_id}/")]
        user_counts = Counter(row["photographer_id"] for row in current)
        count = len(current)
        print(f"{species_id}: resuming at {count}/{target}", flush=True)
        if count >= target:
            continue
        for observation, user, photo, license_code in licensed_candidates(search_name, accepted_name):
            if count >= target:
                break
            observation_id = str(observation["id"])
            photo_id = str(photo["id"])
            user_id = str(user.get("id") or "")
            if (
                not user_id or user_counts[user_id] >= 5
                or observation_id in observations or photo_id in photo_ids
            ):
                continue
            photo_url = str(photo["url"]).replace("/square.", "/large.")
            try:
                content = get_bytes(photo_url)
            except Exception as exc:
                print(f"skip {photo_id}: {exc}", flush=True)
                continue
            if not content.startswith(b"\xff\xd8\xff") or len(content) < 10_000:
                continue
            digest = hashlib.sha256(content).hexdigest()
            if digest in hashes:
                continue
            count += 1
            image = f"{species_id}/IMG_{count:04d}.jpg"
            (root / image).write_bytes(content)
            row = {
                "image": image,
                "group_id": f"inat-observation-{observation_id}",
                "source_type": "iNaturalist",
                "species_name": accepted_name,
                "observation_id": observation_id,
                "photo_id": photo_id,
                "file_page": f"https://www.inaturalist.org/observations/{observation_id}",
                "photo_url": photo_url,
                "license": license_code,
                "artist": str(user.get("name") or user.get("login") or user_id),
                "photographer_id": user_id,
                "observed_on": str(observation.get("observed_on") or ""),
                "sha256": digest,
            }
            rows.append(row)
            hashes.add(digest)
            observations.add(observation_id)
            photo_ids.add(photo_id)
            user_counts[user_id] += 1
            save_rows(root, rows)
            print(f"{species_id}: {count}/{target}", flush=True)
            time.sleep(0.15)
        if count < target:
            print(f"{species_id}: stopped at {count}/{target}; retry to resume", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--existing-root", type=Path, action="append", default=[])
    parser.add_argument("--species", choices=TARGETS, action="append", required=True)
    parser.add_argument("--target-per-class", type=int, default=50)
    args = parser.parse_args()
    if args.target_per_class < 1:
        parser.error("--target-per-class must be positive")
    collect(args.root.resolve(), [path.resolve() for path in args.existing_root], args.species, args.target_per_class)


if __name__ == "__main__":
    main()
