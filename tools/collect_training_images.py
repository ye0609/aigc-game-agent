"""Collect licensed, research-grade mangrove photos from iNaturalist.

Only one photo is selected from each observation. Observation IDs identify
capture sessions; they do not prove different observations show different trees.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
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
SOURCE_FIELDS = [
    "image", "group_id", "source_type", "species_name", "observation_id",
    "photo_id", "file_page", "photo_url", "license", "artist",
    "photographer_id", "observed_on", "sha256",
]


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


def verify_existing(restore_missing: bool = False) -> int:
    source_path = DATA_ROOT / "sources.csv"
    group_path = DATA_ROOT / "groups.csv"
    if not source_path.is_file() or not group_path.is_file():
        raise ValueError("sources.csv 和 groups.csv 必须同时存在")
    with source_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(SOURCE_FIELDS).issubset(reader.fieldnames):
            raise ValueError("sources.csv 缺少必要字段")
        rows = list(reader)
    with group_path.open(encoding="utf-8-sig", newline="") as stream:
        groups = list(csv.DictReader(stream))
    expected_groups = {(row["image"], row["group_id"]) for row in rows}
    if len(expected_groups) != len(rows) or expected_groups != {
        (row.get("image"), row.get("group_id")) for row in groups
    } or len(groups) != len(rows):
        raise ValueError("sources.csv 与 groups.csv 的图片或采集组不一致")
    for row in rows:
        relative = Path(row["image"])
        if not relative.parts or relative.is_absolute() or ".." in relative.parts or relative.parts[0] not in TARGETS:
            raise ValueError(f"来源清单包含无效图片路径：{row['image']}")
        if row["license"] not in ALLOWED_LICENSES:
            raise ValueError(f"来源清单包含不允许的许可证：{row['image']}")
        path = DATA_ROOT / relative
        if not path.is_file():
            if not restore_missing:
                raise FileNotFoundError(f"缺少 {row['image']}；使用 --restore 按来源清单恢复")
            content = get_bytes(row["photo_url"])
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise ValueError(f"下载图片与原始 SHA-256 不一致：{row['image']}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".jpg", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"图片 SHA-256 与来源清单不一致：{row['image']}")
    return len(rows)


def collect_new() -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    if (DATA_ROOT / "sources.csv").exists() or (DATA_ROOT / "groups.csv").exists():
        raise ValueError("来源清单已存在；默认运行会校验清单，不会重新采集")
    if any((DATA_ROOT / species_id).exists() and any((DATA_ROOT / species_id).iterdir()) for species_id in TARGETS):
        raise ValueError("目标图片目录非空；请先保留现有数据并使用干净目录采集")
    source_rows = []
    hashes = set()
    with tempfile.TemporaryDirectory(prefix="recognition-collect-") as staging_dir:
        staging = Path(staging_dir)
        for species_id, (search_name, accepted_name, target) in TARGETS.items():
            destination = staging / species_id
            destination.mkdir(parents=True)
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
        for species_id in TARGETS:
            (DATA_ROOT / species_id).mkdir(exist_ok=True)
            for source in (staging / species_id).iterdir():
                os.replace(source, DATA_ROOT / species_id / source.name)
        with (DATA_ROOT / "groups.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
            writer.writeheader()
            writer.writerows({"image": row["image"], "group_id": row["group_id"]} for row in source_rows)
        with (DATA_ROOT / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=SOURCE_FIELDS)
            writer.writeheader()
            writer.writerows(source_rows)
    return len(source_rows)


def main() -> None:
    global DATA_ROOT
    parser = argparse.ArgumentParser(description="校验或恢复 iNaturalist 红树训练图片")
    parser.add_argument("--root", type=Path, default=DATA_ROOT, help="训练图片和清单目录；采集新批次时应使用空目录")
    parser.add_argument("--restore", action="store_true", help="仅恢复来源清单中缺失且哈希一致的图片")
    args = parser.parse_args()
    DATA_ROOT = args.root.resolve()
    if (DATA_ROOT / "sources.csv").exists() or (DATA_ROOT / "groups.csv").exists():
        count = verify_existing(args.restore)
        print(f"Verified {count} licensed images", flush=True)
    elif args.restore:
        parser.error("--restore 需要已有来源清单")
    else:
        count = collect_new()
        print(f"Collected {count} licensed images", flush=True)


if __name__ == "__main__":
    main()
