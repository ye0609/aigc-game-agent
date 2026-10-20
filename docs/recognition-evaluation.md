# 四类红树识别：首轮迁移学习评估

日期：2026-10-20。使用 `backend/recognition/train_resnet18.py` 固定配方训练一次，输入为当前 147 张已登记许可证和 SHA-256 的 iNaturalist 照片。类别、图片清单和采集组见 `data/species.catalog.json`、`data/recognition/sources.csv` 与 `groups.csv`。

## 方法

- ImageNet 预训练 ResNet18，冻结特征提取层，只训练四分类头；训练组 119 张，每张生成原图与两次训练增强视图。
- 每类 7 张按 `group_id` 留作验证，共 28 张，不参与训练。
- 导出 ONNX 后以 ONNX Runtime 对验证图片推理，并与 PyTorch 输出逐张比对。
- 固定随机种子 `20261018`。本次本机环境：Python 3.11.16、torch 2.14.1、torchvision 0.29.1、onnx 1.23.2、onnxruntime 1.31.0。

## 结果与决定

| 类别 | 验证正确/总数 |
| --- | ---: |
| 木榄 | 5/7 |
| 秋茄 | 3/7 |
| 桐花树 | 6/7 |
| 白骨壤 | 4/7 |
| **合计** | **18/28（0.6429）** |

PyTorch/ONNX 最大 logit 绝对差为 `4.2e-06`。导出一致，但识别准确率低于 `0.75` 门槛，生成的 `metrics.json` 为 `readyForDemo: false`。`GET /api/health` 应报告 `mangroveModelReady: false`，拍照识别继续返回 `fallbackRequired: true`。演示采用手动选物种和 GPS 点位弹卡；不要把它称为自动识别成果。

模型和完整指标位于本机 `backend/recognition/artifacts/model.onnx`、`metrics.json`，被 `.gitignore` 排除；其他机器不会因拉取代码而自动得到模型。当前继续集成无需传递模型。后续若确有更多独立湛江现场照片，再用独立地点验证模型；不要用同一批 28 张验证照片反复调参后宣称达到门槛。

公开照片的 `group_id` 由观察 ID 构成，能隔离同一次观察，但无法证明不同观察一定来自不同个体或地点。当前准确率也不涵盖非红树、未知种、模糊图或现场手机拍摄条件。
