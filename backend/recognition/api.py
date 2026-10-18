"""识别接口：模型就绪时推理，否则返回明确的手动选择兜底信号。

启动：python backend/recognition/api.py
此阶段其余接口仍复用 mock 服务；/api/health 会标明实际状态。
"""

from __future__ import annotations

import json
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.mock.server import MockHandler, error, response  # noqa: E402
from backend.recognition.classifier import CentroidClassifier, image_feature  # noqa: E402


MODEL_PATH = ROOT / "backend/recognition/artifacts/model.npz"
CATALOG_PATH = ROOT / "data/species.catalog.json"
CONFIDENCE_THRESHOLD = 0.65


def fallback_result(mode: str) -> dict:
    return {
        "speciesId": None,
        "name": None,
        "category": mode,
        "confidence": 0.0,
        "alternatives": [],
        "fallbackRequired": True,
    }


def recognize(fields: dict, model_path: Path = MODEL_PATH) -> tuple[int, dict]:
    mode = fields.get("mode")
    if mode not in ("mangrove", "bird"):
        return error("mode 必须是 mangrove 或 bird")
    image = fields.get("_files", {}).get("image")
    if not image or not image.get("content"):
        return error("image 为必填项")

    # 鸟类模型尚未开发，绝不冒充为真实识别结果。
    if mode == "bird" or not model_path.exists():
        return response(fallback_result(mode))

    try:
        feature = image_feature(image["content"])
        model = CentroidClassifier.load(model_path)
        prediction = model.predict(feature)
    except (OSError, ValueError, RuntimeError) as exc:
        return error(f"识别失败：{exc}", 400)

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    species = next((item for item in catalog if item["speciesId"] == prediction["label"]), None)
    if not species:
        return error("模型标签不在物种目录中", 500)
    confidence = prediction["confidence"]
    return response({
        "speciesId": species["speciesId"],
        "name": species["name"],
        "category": mode,
        "confidence": confidence,
        "alternatives": [],
        "fallbackRequired": confidence < CONFIDENCE_THRESHOLD,
    })


class RecognitionHandler(MockHandler):
    server_version = "MangroveRecognition/1.0"

    def do_GET(self):
        if urlparse(self.path).path == "/api/health":
            status, payload = response({
                "service": "hybrid",
                "status": "ok",
                "mangroveModelReady": MODEL_PATH.exists(),
                "birdModelReady": False,
                "otherEndpoints": "mock",
            })
            self.send_json(status, payload)
            return
        super().do_GET()

    def route(self, path: str, fields: dict):
        if path == "/api/recognition/species":
            return recognize(fields)
        return super().route(path, fields)


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), RecognitionHandler)
    print(f"识别联调服务已启动：http://{host}:{port}")
    print(f"红树模型状态：{'已就绪' if MODEL_PATH.exists() else '未就绪，使用手动选择兜底'}")
    print("其他接口仍使用 mock 响应；按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n识别联调服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
