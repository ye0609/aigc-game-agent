"""对单张图片执行识别基线推理。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifier import CentroidClassifier, image_feature
from onnx_model import OnnxClassifier


def main():
    parser = argparse.ArgumentParser(description="识别一张红树图片")
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", type=Path, default=Path("backend/recognition/artifacts/model.onnx"))
    args = parser.parse_args()
    if args.model.suffix == ".onnx":
        labels_path = args.model.with_name("metrics.json")
        metrics = json.loads(labels_path.read_text(encoding="utf-8"))
        model = OnnxClassifier(args.model, metrics["classes"])
        result = model.predict(args.image.read_bytes())
    else:
        model = CentroidClassifier.load(args.model)
        result = model.predict(image_feature(args.image.read_bytes()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
