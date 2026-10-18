"""训练集目录检查工具。"""

from __future__ import annotations

import argparse
import csv
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
    mangroves = [item for item in catalog if item.get("category") == "mangrove"]
    if not mangroves:
        raise ValueError("species.catalog.json 中没有 category=mangrove 的物种")
    return mangroves


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


def load_group_manifest(root: Path, files_by_class: dict[str, list[Path]], manifest_path: Path | None = None) -> dict[Path, str]:
    """Load the required image-to-capture-group mapping for validation splits."""
    manifest_path = manifest_path or root / "groups.csv"
    if not manifest_path.is_file():
        raise ValueError(f"缺少采集分组清单：{manifest_path}（需要 image,group_id 两列）")

    image_to_class = {
        path.relative_to(root).as_posix(): species_id
        for species_id, files in files_by_class.items()
        for path in files
    }
    group_by_path: dict[Path, str] = {}
    seen_images: set[str] = set()
    group_classes: dict[str, str] = {}
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"image", "group_id"}.issubset(reader.fieldnames):
            raise ValueError("groups.csv 必须包含 image,group_id 两列")
        for line_number, row in enumerate(reader, start=2):
            image = (row.get("image") or "").strip().replace("\\", "/")
            group_id = (row.get("group_id") or "").strip()
            image_path = Path(image)
            if not image or image_path.is_absolute() or ".." in image_path.parts:
                raise ValueError(f"groups.csv 第 {line_number} 行 image 必须是数据目录内的相对路径")
            if not group_id:
                raise ValueError(f"groups.csv 第 {line_number} 行 group_id 不能为空")
            if image in seen_images:
                raise ValueError(f"groups.csv 图片重复：{image}")
            if image not in image_to_class:
                raise ValueError(f"groups.csv 图片不存在于训练集：{image}")
            species_id = image_to_class[image]
            if group_id in group_classes and group_classes[group_id] != species_id:
                raise ValueError(f"group_id 必须在整个数据集中唯一：{group_id}")
            group_classes[group_id] = species_id
            seen_images.add(image)
            group_by_path[root / Path(image)] = group_id

    missing = sorted(set(image_to_class) - seen_images)
    if missing:
        preview = ", ".join(missing[:3])
        suffix = " …" if len(missing) > 3 else ""
        raise ValueError(f"groups.csv 缺少 {len(missing)} 张图片的分组：{preview}{suffix}")
    return group_by_path


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
