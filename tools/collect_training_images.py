"""Collect licensed, research-grade mangrove photos from iNaturalist.

Only one photo is selected from each observation. The observation ID is the
capture group so related photos cannot leak across train and validation sets.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "recognition"
API_URL = "https://api.inaturalist.org/v1/observations"
TARGETS = {
    "mangrove-kandelia-obovata": ("Kandelia obovata", "Kandelia obovata", 37),
    "mangrove-avicennia-marina": ("Avicennia marina", "Avicennia marina", 37),
    "mangrove-bruguiera-gymnorrhiza": ("Bruguiera gymnorrhiza", "Bruguiera gymnorhiza", 37),
    "mangrove-aegiceras-corniculatum": ("Aegiceras corniculatum", "Aegiceras corniculatum", 36),
}
ALLOWED_LICENSES = {"cc0", "cc-by", "cc-by-sa"}
MAX_PER_PHOTOGRAPHER = 5
MAX_PAGES = 20


def get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "aigc-game-agent-training/1.0 (educational dataset)"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def get_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "aigc-game-agent-training/1.0 (educational dataset)"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def candidates(search_name: str, accepted_name: str):
    for page in range(1, MAX_PAGES + 1):
        query = urlencode({
            "taxon_name": search_name,
            "photos": "true",
            "quality_grade": "research",
            "per_page": 200,
            "page": page,
            "order": "desc",
            "order_by": "observed_on",
        })
        result = get_json(API_URL + "?" + query)
        observations = result.get("results", [])
        if not observations:
            break
        for observation in observations:
            taxon = observation.get("taxon") or {}
            if taxon.get("name") != accepted_name:
                continue
            user = observation.get("user") or {}
            photos = observation.get("photos") or []
            for photo in photos:
                license_code = str(photo.get("license_code") or "").lower()
                if license_code not in ALLOWED_LICENSES or not photo.get("url"):
                    continue
                yield observation, user, photo, license_code
                break
        time.sleep(0.2)


def main() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    source_rows = []
    hashes = set()
    for species_id, (search_name, accepted_name, target) in TARGETS.items():
        destination = DATA_ROOT / species_id
        destination.mkdir(parents=True, exist_ok=True)
        user_counts = Counter()
        count = 0
        for observation, user, photo, license_code in candidates(search_name, accepted_name):
            if count >= target:
                break
            user_id = user.get("id")
            if user_id is None or user_counts[user_id] >= MAX_PER_PHOTOGRAPHER:
                continue
            photo_url = str(photo["url"]).replace("/square.", "/large.")
            try:
                content = get_bytes(photo_url)
            except Exception as exc:
                print(f"skip {photo.get('id')}: {exc}", flush=True)
                continue
            if not content.startswith(b"\xff\xd8\xff") or len(content) < 10_000:
                continue
            digest = hashlib.sha256(content).hexdigest()
            if digest in hashes:
                continue
            hashes.add(digest)
            count += 1
            user_counts[user_id] += 1
            filename = f"IMG_{count:04d}.jpg"
            (destination / filename).write_bytes(content)
            relative = f"{species_id}/{filename}"
            observation_id = str(observation["id"])
            source_rows.append({
                "image": relative,
                "group_id": f"inat-observation-{observation_id}",
                "source_type": "iNaturalist",
                "species_name": accepted_name,
                "observation_id": observation_id,
                "photo_id": str(photo["id"]),
                "file_page": f"https://www.inaturalist.org/observations/{observation_id}",
                "photo_url": photo_url,
                "license": license_code,
                "artist": str(user.get("name") or user.get("login") or user_id),
                "photographer_id": str(user_id),
                "observed_on": str(observation.get("observed_on") or ""),
                "sha256": digest,
            })
            print(f"{species_id}: {count}/{target}", flush=True)
            time.sleep(0.15)
        if count < target:
            raise RuntimeError(f"{species_id}: only {count}/{target} qualifying images found")

    source_rows.sort(key=lambda row: row["image"])
    with (DATA_ROOT / "groups.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
        writer.writeheader()
        writer.writerows({"image": row["image"], "group_id": row["group_id"]} for row in source_rows)
    with (DATA_ROOT / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source_rows[0]))
        writer.writeheader()
        writer.writerows(source_rows)
    print(f"Collected {len(source_rows)} licensed images", flush=True)


if __name__ == "__main__":
    main()
