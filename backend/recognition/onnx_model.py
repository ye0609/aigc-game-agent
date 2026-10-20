"""Shared image preprocessing and ONNX inference for the four mangrove classes."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


INPUT_SIZE = 224
RESIZE_SHORT_SIDE = 256
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def open_rgb(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, ValueError) as exc:
        raise ValueError(f"无法读取图片：{exc}") from exc


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Match the fixed ResNet18 validation transform, returning NCHW float32."""
    image = open_rgb(image_bytes)
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("图片尺寸无效")
    if width < height:
        new_size = (RESIZE_SHORT_SIDE, int(RESIZE_SHORT_SIDE * height / width))
    else:
        new_size = (int(RESIZE_SHORT_SIDE * width / height), RESIZE_SHORT_SIDE)
    image = image.resize(new_size, Image.Resampling.BILINEAR)
    left = (image.width - INPUT_SIZE) // 2
    top = (image.height - INPUT_SIZE) // 2
    image = image.crop((left, top, left + INPUT_SIZE, top + INPUT_SIZE))
    pixels = np.asarray(image, dtype=np.float32) / 255.0
    pixels = (pixels - MEAN) / STD
    return np.transpose(pixels, (2, 0, 1))[None].copy()


class OnnxClassifier:
    def __init__(self, model_path: Path, labels: list[str]):
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("ONNX 推理需要 onnxruntime；请安装服务端依赖") from exc
        self.labels = labels
        try:
            self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise ValueError(f"ONNX 模型无法加载：{exc}") from exc
        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1 or inputs[0].shape != [1, 3, 224, 224]:
            raise ValueError("ONNX 模型输入或输出结构无效")
        self.input_name = inputs[0].name
        self.output_name = outputs[0].name
        probe = self.session.run([self.output_name], {self.input_name: np.zeros((1, 3, 224, 224), dtype=np.float32)})[0]
        if probe.shape != (1, len(labels)) or not np.isfinite(probe).all():
            raise ValueError("ONNX 模型类别输出无效")

    def logits(self, image_bytes: bytes) -> np.ndarray:
        result = self.session.run([self.output_name], {self.input_name: preprocess(image_bytes)})[0]
        if result.shape != (1, len(self.labels)) or not np.isfinite(result).all():
            raise ValueError("ONNX 模型推理输出无效")
        return result[0]

    def predict(self, image_bytes: bytes) -> dict:
        scores = self.logits(image_bytes)
        probabilities = np.exp(scores - scores.max())
        probabilities /= probabilities.sum()
        index = int(np.argmax(probabilities))
        return {"label": self.labels[index], "confidence": round(float(probabilities[index]), 4)}
