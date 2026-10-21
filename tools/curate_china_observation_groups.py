"""Exclude visually uninformative photos without altering raw source records."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "recognition-china-groups-20261021"
CURATED = ROOT / "data" / "recognition-china-curated-20261021"

# Visual review of the 193-image contact sheets on 2026-10-21. These frames
# show detached material, mud/water, or roots without a visible identifying
# plant. Whole capture groups are dropped where too few useful frames remain.
DROP_GROUPS = {
    "31723402": "detached propagules and distant seedlings",
    "31722657": "mostly water and tiny trees",
    "67071577": "roots without identifying foliage in most frames",
    "68479801": "mostly roots and distant canopy",
    "317550696": "mostly distant landscape",
}
DROP_PHOTOS = {
    "189117465_04.jpg": "detached leaf on mud",
    "189117465_05.jpg": "detached leaf on mud",
    "189462060_06.jpg": "distant stand without identifiable tree",
    "31712709_04.jpg": "mud only",
    "31712709_05.jpg": "mud only",
    "51991176_02.jpg": "roots only",
    "82151637_04.jpg": "roots only",
    "54359344_03.jpg": "roots only",
    "49322828_04.jpg": "roots only",
    "39872864_02.jpg": "exact duplicate image",
}


def main() -> None:
    with (RAW / "sources.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
        fields = list(rows[0])
    for row in rows:
        longitude, latitude = float(row["longitude"]), float(row["latitude"])
        if 118 <= longitude <= 119 and 24 <= latitude <= 25:
            row["region"] = "kinmen"
    filtered = []
    exclusions = []
    seen_hashes = set()
    for row in rows:
        name = Path(row["image"]).name
        reason = DROP_GROUPS.get(row["observation_id"]) or DROP_PHOTOS.get(name)
        if row["sha256"] in seen_hashes:
            reason = "duplicate SHA-256"
        if reason:
            exclusions.append({"image": row["image"], "reason": reason})
            continue
        seen_hashes.add(row["sha256"])
        filtered.append(row)
    counts = Counter(row["group_id"] for row in filtered)
    for row in filtered[:]:
        if counts[row["group_id"]] < 4:
            filtered.remove(row)
            exclusions.append({"image": row["image"], "reason": "fewer than four useful frames in group"})
    CURATED.mkdir(parents=True, exist_ok=True)
    selected_paths = {row["image"] for row in filtered}
    for old_path in CURATED.glob("mangrove-*/*.jpg"):
        relative = old_path.relative_to(CURATED).as_posix()
        if relative in selected_paths:
            continue
        raw_path = RAW / relative
        if not raw_path.is_file() or hashlib.sha256(old_path.read_bytes()).digest() != hashlib.sha256(raw_path.read_bytes()).digest():
            raise ValueError(f"Refusing to remove an unexpected image: {old_path}")
        old_path.unlink()
    for row in filtered:
        destination = CURATED / row["image"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAW / row["image"], destination)
    with (CURATED / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(filtered)
    with (CURATED / "groups.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
        writer.writeheader()
        writer.writerows({"image": row["image"], "group_id": row["group_id"]} for row in filtered)
    with (CURATED / "excluded.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image", "reason"])
        writer.writeheader()
        writer.writerows(exclusions)
    summary = {
        "rawPhotos": len(rows), "curatedPhotos": len(filtered), "excludedPhotos": len(exclusions),
        "curatedGroups": len({row["group_id"] for row in filtered}),
        "bySpecies": dict(Counter(row["species_name"] for row in filtered)),
        "byRegion": {f"{name}:{region}": count for (name, region), count in Counter((row["species_name"], row["region"]) for row in filtered).items()},
    }
    (CURATED / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
