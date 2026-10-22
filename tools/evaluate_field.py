"""Evaluate independent field photos through the running recognition API.

Manifest CSV columns: image,speciesId,siteId,treeId,split. `speciesId` may be
`unknown`; all evaluated rows must have `split=test`. This script cannot prove
independence by itself: keep tested trees/sites out of training and tuning.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/species.catalog.json"
REQUIRED = {"image", "speciesId", "siteId", "treeId", "split"}
UNKNOWN = "unknown"
FALLBACK = "fallback"


def read_manifest(path: Path) -> list[dict]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    allowed = {item["speciesId"] for item in catalog if item["category"] == "mangrove"}
    rows = []
    images = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
            raise ValueError(f"manifest 必须包含列：{', '.join(sorted(REQUIRED))}")
        for line, row in enumerate(reader, start=2):
            label = (row["speciesId"] or "").strip()
            if label not in allowed | {UNKNOWN}:
                raise ValueError(f"第 {line} 行 speciesId 无效：{label}")
            if (row["split"] or "").strip().lower() != "test":
                raise ValueError(f"第 {line} 行不是独立 test 集")
            if not (row["siteId"] or "").strip() or not (row["treeId"] or "").strip():
                raise ValueError(f"第 {line} 行缺少 siteId/treeId")
            image = Path((row["image"] or "").strip())
            if not image.is_absolute():
                image = path.parent / image
            image = image.resolve()
            if not image.is_file() or image.stat().st_size == 0:
                raise ValueError(f"第 {line} 行图片缺失或为空：{image}")
            if image in images:
                raise ValueError(f"第 {line} 行图片重复：{image}")
            images.add(image)
            rows.append({"image": image, "speciesId": label,
                         "siteId": row["siteId"].strip(), "treeId": row["treeId"].strip()})
    if not rows:
        raise ValueError("manifest 没有测试图片")
    return rows


def upload(base_url: str, image: Path, token: str | None) -> dict:
    boundary = uuid.uuid4().hex
    media_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"mode\"\r\n\r\nmangrove\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
        f"filename=\"field-photo{image.suffix.lower()}\"\r\n"
        f"Content-Type: {media_type}\r\n\r\n"
    ).encode() + image.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base_url.rstrip("/") + "/api/recognition/species",
                      data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=40) as response:
            payload = json.load(response)
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"接口请求失败：{image}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError(f"识别接口返回错误：{image}: {payload}")
    result = payload.get("data")
    if not isinstance(result, dict) or not isinstance(result.get("fallbackRequired"), bool):
        raise RuntimeError(f"识别接口缺少有效结果：{image}")
    return result


def evaluate(rows: list[dict], base_url: str, token: str | None) -> dict:
    per_class = defaultdict(lambda: {"total": 0, "correct": 0, "fallback": 0})
    raw_confusion = defaultdict(Counter)
    decision_confusion = defaultdict(Counter)
    details = []
    fallback_count = 0
    unknown_count = 0
    unknown_fallback = 0
    for row in rows:
        result = upload(base_url, row["image"], token)
        actual = row["speciesId"]
        predicted = result.get("speciesId") or UNKNOWN
        fallback = result["fallbackRequired"]
        if fallback:
            fallback_count += 1
        if actual == UNKNOWN:
            unknown_count += 1
            unknown_fallback += int(fallback)
        else:
            per_class[actual]["total"] += 1
            per_class[actual]["correct"] += int(predicted == actual)
            per_class[actual]["fallback"] += int(fallback)
        raw_confusion[actual][predicted] += 1
        decision_confusion[actual][FALLBACK if fallback else predicted] += 1
        details.append({"image": str(row["image"]), "actual": actual,
                        "predicted": predicted, "confidence": result.get("confidence"),
                        "fallbackRequired": fallback, "siteId": row["siteId"],
                        "treeId": row["treeId"]})
    known_total = sum(item["total"] for item in per_class.values())
    known_correct = sum(item["correct"] for item in per_class.values())
    return {
        "scope": "independent-field-test-manifest-supplied-by-user",
        "total": len(rows), "knownTotal": known_total, "unknownTotal": unknown_count,
        "knownTop1Accuracy": known_correct / known_total if known_total else None,
        "perSpeciesRecall": {
            species: {"samples": counts["total"], "recall": counts["correct"] / counts["total"],
                      "fallbackRate": counts["fallback"] / counts["total"]}
            for species, counts in sorted(per_class.items())
        },
        "fallbackRate": fallback_count / len(rows),
        "unknownFallbackRate": unknown_fallback / unknown_count if unknown_count else None,
        "unknownFalseAcceptRate": 1 - unknown_fallback / unknown_count if unknown_count else None,
        "rawTop1Confusion": {actual: dict(counts) for actual, counts in sorted(raw_confusion.items())},
        "decisionConfusion": {actual: dict(counts) for actual, counts in sorted(decision_confusion.items())},
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="现场独立测试照片 CSV")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, help="可选 JSON 输出路径")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parser.error("--base-url 必须是 HTTP(S) 地址")
    report = evaluate(read_manifest(args.manifest), args.base_url, os.getenv("API_TOKEN"))
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
