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

from backend.mock.server import MockHandler, error, has_valid_image, response, validate_bind_security  # noqa: E402
from backend.recognition.classifier import CentroidClassifier, file_sha256, image_feature  # noqa: E402


MODEL_PATH = ROOT / "backend/recognition/artifacts/model.npz"
METRICS_PATH = ROOT / "backend/recognition/artifacts/metrics.json"
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


def load_ready_model(model_path: Path = MODEL_PATH, metrics_path: Path | None = None):
    metrics_path = metrics_path or (METRICS_PATH if model_path == MODEL_PATH else model_path.with_name("metrics.json"))
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"评估指标文件无效：{exc}") from exc
    if not isinstance(metrics, dict) or metrics.get("readyForDemo") is not True:
        raise ValueError("模型评估未达到演示就绪条件")
    expected_sha256 = metrics.get("modelSha256")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("评估指标缺少有效的 modelSha256")
    try:
        actual_sha256 = file_sha256(model_path)
    except OSError as exc:
        raise ValueError(f"模型文件不可读：{exc}") from exc
    if actual_sha256 != expected_sha256.lower():
        raise ValueError("模型文件与评估指标不匹配")
    model = CentroidClassifier.load(model_path)
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or any(not isinstance(item, dict) for item in catalog):
        raise ValueError("物种目录格式无效")
    mangroves = [item for item in catalog if item.get("category") == "mangrove"]
    if any(not isinstance(item.get("speciesId"), str) or not item["speciesId"] for item in mangroves):
        raise ValueError("红树物种目录缺少有效 speciesId")
    expected_labels = {item["speciesId"] for item in mangroves}
    if not expected_labels or set(model.labels) != expected_labels:
        raise ValueError("模型类别与当前红树物种目录不匹配")
    return model, catalog


def model_is_ready(model_path: Path = MODEL_PATH) -> bool:
    try:
        load_ready_model(model_path)
    except (OSError, ValueError):
        return False
    return True


def recognize(fields: dict, model_path: Path = MODEL_PATH) -> tuple[int, dict]:
    mode = fields.get("mode")
    if mode not in ("mangrove", "bird"):
        return error("mode 必须是 mangrove 或 bird")
    if not has_valid_image(fields):
        return error("image 为必填项且文件内容不能为空")
    image = fields["_files"]["image"]

    # 鸟类模型尚未开发，绝不冒充为真实识别结果。
    if mode == "bird":
        return response(fallback_result(mode))

    try:
        model, catalog = load_ready_model(model_path)
    except (OSError, ValueError):
        return response(fallback_result(mode))

    try:
        feature = image_feature(image["content"])
        prediction = model.predict(feature)
    except (ValueError, RuntimeError) as exc:
        return error(f"识别失败：{exc}", 400)

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
        if not self.authorized():
            self.reject_unauthorized()
            return
        if urlparse(self.path).path == "/api/health":
            status, payload = response({
                "service": "hybrid",
                "status": "ok",
                "mangroveModelReady": model_is_ready(),
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
    token = os.environ.get("API_TOKEN", "")
    validate_bind_security(host, token)
    server = ThreadingHTTPServer((host, port), RecognitionHandler)
    server.api_token = token
    print(f"识别联调服务已启动：http://{host}:{port}")
    print(f"红树模型状态：{'已就绪' if model_is_ready() else '未就绪，使用手动选择兜底'}")
    print("其他接口仍使用 mock 响应；按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n识别联调服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
