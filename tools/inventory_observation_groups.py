"""Inventory licensed multi-photo iNaturalist observations for two mangroves."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlencode

from collect_training_images import ALLOWED_LICENSES, API_URL, get_json


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "recognition-china-observation-inventory-20261021.json"
TARGETS = ("Kandelia obovata", "Avicennia marina")
PLACE_IDS = (6903, 7613, 7887)  # China, Hong Kong, Taiwan in iNaturalist


def inventory(name: str) -> list[dict]:
    query = {
        "taxon_name": name,
        "photos": "true",
        "quality_grade": "research",
        "photo_license": "cc0,cc-by,cc-by-sa",
        "per_page": 50,
        "order": "desc",
        "order_by": "observed_on",
    }
    rows = []
    seen = set()
    for place_id in PLACE_IDS:
        page = 1
        while True:
            result = get_json(API_URL + "?" + urlencode({**query, "place_id": place_id, "page": page}))
            for obs in result.get("results", []):
                if str(obs["id"]) in seen or (obs.get("taxon") or {}).get("name") != name:
                    continue
                photos = [
                    {"id": str(photo["id"]), "license": str(photo.get("license_code") or "").lower(), "url": photo["url"]}
                    for photo in obs.get("photos") or []
                    if str(photo.get("license_code") or "").lower() in ALLOWED_LICENSES and photo.get("url")
                ]
                if not photos:
                    continue
                geo = obs.get("geojson") or {}
                coordinates = geo.get("coordinates") or []
                user = obs.get("user") or {}
                rows.append({
                    "id": str(obs["id"]), "species": name,
                    "place_guess": obs.get("place_guess") or "",
                    "coordinates": coordinates,
                    "photographer_id": str(user.get("id") or ""),
                    "artist": str(user.get("name") or user.get("login") or ""),
                    "observed_on": str(obs.get("observed_on") or ""),
                    "photos": photos,
                })
                seen.add(str(obs["id"]))
            print(name, place_id, page, len(rows), "of", result.get("total_results"), flush=True)
            if page * query["per_page"] >= int(result.get("total_results", 0)) or not result.get("results"):
                break
            page += 1
    return rows


def main() -> None:
    saved = {}
    if OUTPUT.exists():
        saved = json.loads(OUTPUT.read_text(encoding="utf-8"))
    for name in TARGETS:
        if name in saved:
            continue
        saved[name] = inventory(name)
        OUTPUT.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, rows in saved.items():
        print(name, "observations", len(rows), "photos", sum(len(row["photos"]) for row in rows), flush=True)
        print("photos-per-observation", dict(Counter(len(row["photos"]) for row in rows)), flush=True)
        places = defaultdict(lambda: [0, 0])
        for row in rows:
            key = row["place_guess"].split(",")[-1].strip()
            places[key][0] += 1
            places[key][1] += len(row["photos"])
        print("top places", sorted(places.items(), key=lambda item: item[1][1], reverse=True)[:15], flush=True)


if __name__ == "__main__":
    main()
