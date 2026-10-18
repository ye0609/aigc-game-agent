"""训练集目录检查工具。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_catalog(catalog_path: Path) -> list[dict]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("species.catalog.json 必须是非空数组")
    ids = [item.get("speciesId") for item in catalog]
    if any(not item_id for item_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("speciesId 必须存在且不能重复")
    return catalog


def collect_images(root: Path, catalog: list[dict]) -> dict[str, list[Path]]:
    result = {}
    for item in catalog:
        species_id = item["speciesId"]
        directory = root / species_id
        files = sorted(path for path in directory.glob("**/*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
        result[species_id] = files
    return result


def validate_dataset(root: Path, catalog_path: Path, min_per_class: int = 30) -> dict:
    catalog = load_catalog(catalog_path)
    files_by_class = collect_images(root, catalog)
    counts = {species_id: len(files) for species_id, files in files_by_class.items()}
    missing = [species_id for species_id, count in counts.items() if count < min_per_class]
    return {
        "root": str(root),
        "classes": len(catalog),
        "counts": counts,
        "total": sum(counts.values()),
        "minPerClass": min_per_class,
        "ready": not missing,
        "missing": missing,
        "files": files_by_class,
    }


def main():
    parser = argparse.ArgumentParser(description="检查红树识别训练集")
    parser.add_argument("--root", type=Path, default=Path("data/recognition"))
    parser.add_argument("--catalog", type=Path, default=Path("data/species.catalog.json"))
    parser.add_argument("--min-per-class", type=int, default=30)
    args = parser.parse_args()
    result = validate_dataset(args.root, args.catalog, args.min_per_class)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, ensure_ascii=False, indent=2))
    if not result["ready"]:
        raise SystemExit("训练集未就绪：每个类别都需要达到 --min-per-class 张图片")


if __name__ == "__main__":
    main()
