"""Activate the expanded ResNet18 candidate for an explicitly requested local demo.

This does not declare field validation. The training report stays unchanged and
the installed model plus activation metrics are local, Git-ignored artifacts.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.recognition.api import model_is_ready  # noqa: E402
from backend.recognition.classifier import file_sha256  # noqa: E402

SOURCE = ROOT / "data" / "recognition-balance-20261021"
DESTINATION = ROOT / "backend" / "recognition" / "artifacts"
SPLIT = "new-batch-photographer-holdout-no-historical-author-overlap"


def activate() -> dict:
    candidate = SOURCE / "resnet18-expanded-candidate.onnx"
    report_path = SOURCE / "expanded-resnet18-metrics.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("readyForDemo") is not False:
        raise ValueError("原始实验报告必须保留 readyForDemo: false")
    accuracy = report.get("developmentAccuracy")
    if (isinstance(accuracy, bool) or not isinstance(accuracy, (int, float))
            or accuracy < 0.75 or report.get("developmentSamples", 0) < 20):
        raise ValueError("开发集结果未达到本地演示门槛")
    labels = report.get("classes")
    catalog = json.loads((ROOT / "data" / "species.catalog.json").read_text(encoding="utf-8"))
    expected = {item["speciesId"] for item in catalog if item["category"] == "mangrove"}
    if not isinstance(labels, list) or len(labels) != len(expected) or set(labels) != expected:
        raise ValueError("模型类别顺序缺失或与目录不符")
    if file_sha256(candidate) != report.get("modelSha256"):
        raise ValueError("候选 ONNX 与实验报告的 SHA-256 不匹配")
    if candidate.stat().st_size != report.get("modelBytes"):
        raise ValueError("候选 ONNX 大小与实验报告不符")

    DESTINATION.mkdir(parents=True, exist_ok=True)
    destination_model = DESTINATION / "model.onnx"
    destination_metrics = DESTINATION / "metrics.json"
    temporary_model = DESTINATION / "model.activating.onnx"
    temporary_metrics = DESTINATION / "metrics.activating.json"
    shutil.copyfile(candidate, temporary_model)
    if file_sha256(temporary_model) != report["modelSha256"]:
        temporary_model.unlink(missing_ok=True)
        raise ValueError("复制后的 ONNX 校验失败")
    metrics = dict(report)
    metrics.update({
        "model": "resnet18-expanded-onnx-v1",
        "validationAccuracy": accuracy,
        "validationSplit": SPLIT,
        "readyForDemo": True,
        "demoActivation": "local-demo-user-approved-2026-10-21",
        "deploymentNote": (
            "Enabled for local demonstration at user request. The 29-image online-photo "
            "development result is not Zhanjiang field validation. Keep manual fallback."
        ),
    })
    temporary_metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_model.replace(destination_model)
    temporary_metrics.replace(destination_metrics)
    if not model_is_ready():
        raise RuntimeError("激活后后端仍拒绝模型，请检查部署指标")
    return {"modelSha256": metrics["modelSha256"], "developmentAccuracy": accuracy,
            "developmentSamples": report["developmentSamples"], "localDemoReady": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-demo", action="store_true", help="确认仅为本地演示启用，非现场验收")
    args = parser.parse_args()
    if not args.local_demo:
        parser.error("本脚本需要显式传入 --local-demo")
    print(json.dumps(activate(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
