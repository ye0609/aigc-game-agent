"""基于图像颜色和低分辨率空间特征的可替换识别基线。

这是第 2 周的可运行基线，目的是先得到可测的混淆矩阵和兜底信号；拿到样本后可替换为迁移学习模型，接口输出保持不变。
"""

from __future__ import annotations

import io
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np

try:
    from PIL import Image
except ImportError:  # pragma: no cover - 在未安装训练依赖的电脑上给出明确提示
    Image = None


FEATURE_SIZE = 816


def file_sha256(path: Path) -> str:
    """Return the digest used to bind a metrics file to one model artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_feature(image_bytes: bytes) -> np.ndarray:
    if Image is None:
        raise RuntimeError("识别需要 Pillow：请先运行 pip install -r backend/recognition/requirements.txt")
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"无法读取图片：{exc}") from exc
    image = image.resize((16, 16))
    pixels = np.asarray(image, dtype=np.float32) / 255.0
    spatial = pixels.reshape(-1)
    histograms = [np.histogram(pixels[:, :, channel], bins=16, range=(0, 1), density=True)[0] / 16 for channel in range(3)]
    feature = np.concatenate([spatial, *histograms]).astype(np.float32)
    if feature.size != FEATURE_SIZE:
        raise ValueError(f"图像特征长度错误：{feature.size}")
    return feature


class CentroidClassifier:
    def __init__(self, labels: list[str], centroids: np.ndarray, counts: np.ndarray):
        self.labels = labels
        self.centroids = centroids.astype(np.float32)
        self.counts = counts.astype(np.int64)

    @classmethod
    def fit(cls, features: np.ndarray, labels: list[str], label_order: list[str]):
        centroids = []
        counts = []
        for label in label_order:
            selected = features[np.array(labels) == label]
            if len(selected) == 0:
                raise ValueError(f"类别没有训练样本：{label}")
            centroids.append(selected.mean(axis=0))
            counts.append(len(selected))
        return cls(label_order, np.vstack(centroids), np.array(counts))

    def predict(self, feature: np.ndarray) -> dict:
        distances = np.linalg.norm(self.centroids - feature, axis=1)
        order = np.argsort(distances)
        best_index = int(order[0])
        # 归一化最近与次近距离的差；这是兜底分数，不是校准概率。
        best_distance = float(distances[order[0]])
        second_distance = float(distances[order[1]]) if len(order) > 1 else best_distance
        confidence = float(np.clip((second_distance - best_distance) / (second_distance + 1e-6), 0.0, 0.99))
        return {
            "label": self.labels[best_index],
            "confidence": round(confidence, 4),
            "distances": {self.labels[index]: round(float(distances[index]), 4) for index in order},
        }

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, labels=np.array(self.labels), centroids=self.centroids, counts=self.counts)

    @classmethod
    def load(cls, path: Path):
        try:
            with np.load(path, allow_pickle=False) as data:
                labels = data["labels"].tolist()
                centroids = data["centroids"]
                counts = data["counts"]
        except (OSError, ValueError, KeyError, IndexError, EOFError, zipfile.BadZipFile) as exc:
            raise ValueError(f"模型文件无效：{exc}") from exc
        if not isinstance(labels, list) or not labels or not all(isinstance(label, str) and label for label in labels):
            raise ValueError("模型文件中的类别列表无效")
        if (
            len(labels) != len(set(labels))
            or centroids.ndim != 2
            or centroids.shape != (len(labels), FEATURE_SIZE)
            or not np.issubdtype(centroids.dtype, np.floating)
            or not np.isfinite(centroids).all()
            or counts.ndim != 1
            or len(counts) != len(labels)
            or not np.issubdtype(counts.dtype, np.integer)
            or np.any(counts <= 0)
        ):
            raise ValueError("模型文件中的类别、特征或样本数不匹配")
        return cls(labels, centroids, counts)


def write_metrics(path: Path, metrics: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
