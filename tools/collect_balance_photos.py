"""Collect open-licensed iNaturalist photos for four mangrove taxa.

Searches China/Hong Kong/Taiwan first, then worldwide open records if needed.
One photo per observation is used; metadata and checksums are retained.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode

from collect_training_images import ALLOWED_LICENSES, API_URL, get_bytes, get_json

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "mangrove-aegiceras-corniculatum": "Aegiceras corniculatum",
    "mangrove-avicennia-marina": "Avicennia marina",
    # The catalog uses the legacy spelling "gymnorhiza"; iNaturalist returns
    # that accepted taxon spelling even when queried by the corrected spelling.
    "mangrove-bruguiera-gymnorrhiza": "Bruguiera gymnorhiza",
    "mangrove-kandelia-obovata": "Kandelia obovata",
}
SEARCH_NAMES = {"Bruguiera gymnorhiza": "Bruguiera gymnorrhiza"}
FIELDS = ["image", "group_id", "source_type", "species_name", "observation_id", "photo_id",
          "file_page", "photo_url", "license", "artist", "photographer_id", "observed_on",
          "sha256", "latitude", "longitude", "region", "search_scope"]
PLACE_IDS = (6903, 7613, 7887)


def rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def china_range(coordinates) -> bool:
    if not coordinates or len(coordinates) != 2:
        return False
    lon, lat = coordinates
    return 108 <= lon <= 123 and 18 <= lat <= 54


def region_for(lon: float, lat: float) -> str:
    if 113.5 <= lon <= 115 and 22 <= lat <= 23:
        return "hong-kong"
    if 118 <= lon <= 119 and 24 <= lat <= 25:
        return "kinmen"
    if lon >= 121 and lat >= 24.5:
        return "taiwan-north"
    if 119 <= lon <= 121 and lat < 24.5:
        return "taiwan-west-south"
    if lon >= 119:
        return "taiwan-other"
    if lon < 120 and 18 <= lat <= 24:
        return "mainland-south"
    return "china-range-other"


def observations(name: str, place_id: int | None):
    query = {"taxon_name": SEARCH_NAMES.get(name, name), "photos": "true", "quality_grade": "research",
             "photo_license": "cc0,cc-by,cc-by-sa", "per_page": 200,
             "order": "desc", "order_by": "observed_on"}
    if place_id is not None:
        query["place_id"] = place_id
    first = get_json(API_URL + "?" + urlencode({**query, "page": 1}))
    pages = min(30, (int(first.get("total_results", 0)) + 199) // 200)
    print(f"query {query['taxon_name']} scope={place_id or 'global'} observations={first.get('total_results', 0)}", flush=True)
    for page in range(1, pages + 1):
        result = first if page == 1 else get_json(API_URL + "?" + urlencode({**query, "page": page}))
        for obs in result.get("results", []):
            if (obs.get("taxon") or {}).get("name") != name:
                continue
            yield obs
        time.sleep(0.12)


def collect(root: Path, existing_roots: list[Path], target: int, max_per_author: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if (root / "curated.csv").exists():
        raise ValueError("该批次已人工筛选；使用 --restore 校验或在新目录采集，避免覆盖筛选清单")
    found = rows(root / "sources.csv")
    old = [row for source_root in existing_roots for row in rows(source_root / "sources.csv")]
    known_obs = {row.get("observation_id", "") for row in old + found}
    known_photos = {row.get("photo_id", "") for row in old + found}
    known_hashes = {row.get("sha256", "") for row in old + found}

    for species_id, species_name in TARGETS.items():
        current = [row for row in found if row["image"].startswith(species_id + "/")]
        per_author = {}
        for row in current:
            per_author[row["photographer_id"]] = per_author.get(row["photographer_id"], 0) + 1
        directory = root / species_id
        directory.mkdir(parents=True, exist_ok=True)
        count = len(current)
        # Prefer records inside the broader China range; use global observations
        # only when those do not supply enough distinct groups.
        scopes = [(place_id, "china-range") for place_id in PLACE_IDS] + [(None, "global")]
        seen_scope_obs = set()
        for place_id, scope in scopes:
            if count >= target:
                break
            for obs in observations(species_name, place_id):
                obs_id = str(obs.get("id") or "")
                if not obs_id or obs_id in known_obs or obs_id in seen_scope_obs:
                    continue
                seen_scope_obs.add(obs_id)
                coordinates = (obs.get("geojson") or {}).get("coordinates") or []
                if scope == "global" and china_range(coordinates):
                    continue
                user = obs.get("user") or {}
                author_id = str(user.get("id") or "")
                if not author_id or per_author.get(author_id, 0) >= max_per_author:
                    continue
                selected = next((p for p in (obs.get("photos") or [])
                                 if str(p.get("license_code") or "").lower() in ALLOWED_LICENSES and p.get("url")), None)
                if not selected:
                    continue
                photo_id = str(selected.get("id") or "")
                if not photo_id or photo_id in known_photos:
                    continue
                photo_url = str(selected["url"]).replace("/square.", "/large.")
                try:
                    content = get_bytes(photo_url)
                except Exception as exc:
                    print(f"skip photo={photo_id}: {exc}", flush=True)
                    continue
                if not content.startswith(b"\xff\xd8\xff") or len(content) < 10_000:
                    continue
                digest = hashlib.sha256(content).hexdigest()
                if digest in known_hashes:
                    continue
                count += 1
                image = f"{species_id}/INAT_{count:04d}.jpg"
                (directory / Path(image).name).write_bytes(content)
                lon = coordinates[0] if len(coordinates) == 2 else ""
                lat = coordinates[1] if len(coordinates) == 2 else ""
                found.append({"image": image, "group_id": f"inat-observation-{obs_id}",
                    "source_type": "iNaturalist", "species_name": species_name,
                    "observation_id": obs_id, "photo_id": photo_id,
                    "file_page": f"https://www.inaturalist.org/observations/{obs_id}",
                    "photo_url": photo_url,
                    "license": str(selected["license_code"]).lower(),
                    "artist": str(user.get("name") or user.get("login") or author_id),
                    "photographer_id": author_id, "observed_on": str(obs.get("observed_on") or ""),
                    "sha256": digest, "latitude": str(lat), "longitude": str(lon),
                    "region": region_for(float(lon), float(lat)) if lon != "" else "unknown",
                    "search_scope": scope})
                known_obs.add(obs_id); known_photos.add(photo_id); known_hashes.add(digest)
                per_author[author_id] = per_author.get(author_id, 0) + 1
                tmp = root / "sources.csv.tmp"
                with tmp.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=FIELDS)
                    writer.writeheader(); writer.writerows(found)
                tmp.replace(root / "sources.csv")
                with (root / "groups.csv.tmp").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
                    writer.writeheader(); writer.writerows({"image": r["image"], "group_id": r["group_id"]} for r in found)
                (root / "groups.csv.tmp").replace(root / "groups.csv")
                print(f"{species_id} {count}/{target} ({scope}) {image}", flush=True)
                time.sleep(0.1)
                if count >= target:
                    break
            if count < target and scope != "global":
                continue
        print(f"{species_id}: collected {count}/{target}", flush=True)

    summary = {species_id: {"photos": sum(row["image"].startswith(species_id + "/") for row in found),
                            "groups": len({row["group_id"] for row in found if row["image"].startswith(species_id + "/")})}
               for species_id in TARGETS}
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)




def restore(root: Path) -> None:
    found = rows(root / "sources.csv")
    if not found:
        raise ValueError(f"恢复需要已有来源清单：{root / 'sources.csv'}")
    restored = 0
    for row in found:
        relative = Path(row["image"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] not in TARGETS:
            raise ValueError(f"来源清单包含无效图片路径：{row['image']}")
        if row.get("license", "").lower() not in ALLOWED_LICENSES:
            raise ValueError(f"来源清单包含不允许的许可证：{row['image']}")
        path = root / relative
        if path.is_file():
            content = path.read_bytes()
        else:
            content = get_bytes(row["photo_url"])
            if not content.startswith(b"\xff\xd8\xff"):
                raise ValueError(f"下载内容不是 JPEG：{row['image']}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            restored += 1
        if hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise ValueError(f"图片 SHA-256 与来源清单不一致：{row['image']}")
        time.sleep(0.05)
    print(f"Verified {len(found)} licensed records; restored {restored} images", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "data" / "recognition-balance-20261021")
    parser.add_argument("--existing-root", type=Path, action="append", default=[])
    parser.add_argument("--target-per-class", type=int, default=60)
    parser.add_argument("--max-per-author", type=int, default=15,
                        help="每类每位摄影者最多使用的独立观察组；较高值可能导致作者分布偏斜")
    parser.add_argument("--restore", action="store_true", help="从已有来源清单恢复缺失照片并校验 SHA-256")
    args = parser.parse_args()
    if args.target_per_class < 1 or args.max_per_author < 1:
        parser.error("target-per-class 和 max-per-author 必须为正整数")
    root = args.root.resolve()
    if args.restore:
        restore(root)
    else:
        collect(root, [p.resolve() for p in args.existing_root], args.target_per_class, args.max_per_author)


if __name__ == "__main__":
    main()
