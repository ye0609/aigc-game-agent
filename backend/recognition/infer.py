"""对单张图片执行识别基线推理。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifier import CentroidClassifier, image_feature


def main():
    parser = argparse.ArgumentParser(description="识别一张红树图片")
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", type=Path, default=Path("backend/recognition/artifacts/model.npz"))
    args = parser.parse_args()
    model = CentroidClassifier.load(args.model)
    print(json.dumps(model.predict(image_feature(args.image.read_bytes())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
