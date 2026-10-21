"""Materialize grouped, licensed China-range iNaturalist observations.

An observation is treated as one capture group. All selected photos from an
observation remain in that group, so grouped validation cannot split one tree
across training and validation. This is a research expansion directory and
never replaces the deployed model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from collect_training_images import ALLOWED_LICENSES, SOURCE_FIELDS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "data" / "recognition-china-observation-inventory-20261021.json"
DEFAULT_OUTPUT = ROOT / "data" / "recognition-china-groups-20261021"
SPECIES = {
    "Kandelia obovata": "mangrove-kandelia-obovata",
    "Avicennia marina": "mangrove-avicennia-marina",
}


def get_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "aigc-game-agent-training/1.0 (educational dataset)"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def country_range(row: dict) -> bool:
    coordinates = row.get("coordinates") or []
    if len(coordinates) != 2:
        return False
    longitude, latitude = coordinates
    # China-range coastal records used here: mainland coast, Hong Kong,
    # Kinmen and Taiwan. The broad box excludes the Japan and India records.
    return 108 <= longitude <= 123 and 18 <= latitude <= 54


def region(row: dict) -> str:
    longitude, latitude = row["coordinates"]
    if 113.5 <= longitude <= 115 and 22 <= latitude <= 23:
        return "hong-kong"
    if 118 <= longitude <= 119 and 24 <= latitude <= 25:
        return "kinmen"
    if longitude >= 121 and latitude >= 24.5:
        return "taiwan-north"
    if 119 <= longitude <= 121 and latitude < 24.5:
        return "taiwan-west-south"
    if longitude >= 119:
        return "taiwan-other"
    return "mainland-south"


def read_existing_roots(roots: list[Path]) -> tuple[set[str], set[str]]:
    observations: set[str] = set()
    hashes: set[str] = set()
    for root in roots:
        source = root / "sources.csv"
        if not source.exists():
            continue
        with source.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                observations.add(str(row.get("observation_id") or ""))
                hashes.add(str(row.get("sha256") or ""))
    return observations, hashes


def write_manifests(root: Path, rows: list[dict[str, str]]) -> None:
    for name, fields in (("sources.csv", SOURCE_FIELDS + ["latitude", "longitude", "region"]), ("groups.csv", ["image", "group_id"])):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda row: row["image"]))
        os.replace(temporary, root / name)


def collect(inventory_path: Path, output: Path, existing_roots: list[Path], max_per_group: int) -> None:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    existing_observations, existing_hashes = read_existing_roots(existing_roots)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    seen_hashes: set[str] = set(existing_hashes)
    summary: dict[str, dict[str, int]] = {}
    for species_name, species_id in SPECIES.items():
        candidates = [
            row for row in inventory.get(species_name, [])
            if country_range(row) and len(row.get("photos") or []) >= 4
        ]
        candidates.sort(key=lambda row: (-len(row["photos"]), row["id"]))
        count_groups = 0
        count_photos = 0
        count_skipped = 0
        for observation in candidates:
            observation_id = str(observation["id"])
            if observation_id in existing_observations:
                count_skipped += 1
                continue
            photos = [photo for photo in observation["photos"] if photo.get("license") in ALLOWED_LICENSES]
            photos = photos[:max_per_group]
            downloaded: list[tuple[dict, bytes, str]] = []
            group_hashes: set[str] = set()
            for photo in photos:
                try:
                    content = get_bytes(str(photo["url"]).replace("/square.", "/large."))
                except Exception as exc:
                    print(f"skip {photo['id']}: {exc}", flush=True)
                    continue
                if not content.startswith(b"\xff\xd8\xff") or len(content) < 10_000:
                    continue
                digest = hashlib.sha256(content).hexdigest()
                if digest in seen_hashes or digest in group_hashes:
                    continue
                downloaded.append((photo, content, digest))
                group_hashes.add(digest)
            if len(downloaded) < 4:
                count_skipped += 1
                continue
            group_id = f"inat-observation-{observation_id}"
            longitude, latitude = observation["coordinates"]
            group_region = region(observation)
            for index, (photo, content, digest) in enumerate(downloaded, start=1):
                image = f"{species_id}/{observation_id}_{index:02d}.jpg"
                target = output / image
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                rows.append({
                    "image": image,
                    "group_id": group_id,
                    "source_type": "iNaturalist",
                    "species_name": species_name,
                    "observation_id": observation_id,
                    "photo_id": str(photo["id"]),
                    "file_page": f"https://www.inaturalist.org/observations/{observation_id}",
                    "photo_url": str(photo["url"]).replace("/square.", "/large."),
                    "license": str(photo["license"]),
                    "artist": observation.get("artist", ""),
                    "photographer_id": observation.get("photographer_id", ""),
                    "observed_on": observation.get("observed_on", ""),
                    "sha256": digest,
                    "latitude": str(latitude),
                    "longitude": str(longitude),
                    "region": group_region,
                })
                seen_hashes.add(digest)
            count_groups += 1
            count_photos += len(downloaded)
        summary[species_id] = {
            "candidateGroups": len(candidates),
            "downloadedGroups": count_groups,
            "downloadedPhotos": count_photos,
            "skippedGroups": count_skipped,
        }
    write_manifests(output, rows)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--existing-root", type=Path, action="append", default=[])
    parser.add_argument("--max-per-group", type=int, default=8)
    args = parser.parse_args()
    if not 4 <= args.max_per_group <= 8:
        parser.error("--max-per-group must be between 4 and 8")
    collect(args.inventory.resolve(), args.output.resolve(), [path.resolve() for path in args.existing_root], args.max_per_group)


if __name__ == "__main__":
    main()
