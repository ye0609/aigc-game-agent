# EfficientNet-B0 识别实验

日期：2026-10-21。使用与 ResNet18 对照实验相同的 238 张训练图、同一个 47 张摄影者分组开发集、同一个 56 张固定留出集。留出集已用于先前多轮模型比较，因此结果是探索性参考，不能当作独立现场验收。

## 结果

开发集比较三种配置：

| 配置 | 开发集正确/总数 | 准确率 |
| --- | ---: | ---: |
| 冻结 EfficientNet-B0，仅训练分类头 | 20/47 | 42.55% |
| 微调最后一个 MBConv block | 30/47 | 63.83% |
| 类别加权并微调最后一个 block | 26/47 | 55.32% |

按开发集选定“微调最后一个 MBConv block”，再用全部 238 张训练图重训：

| 模型 | 固定留出集 | ONNX 大小 | 本机 CPU ONNX 推理 |
| --- | ---: | ---: | ---: |
| 之前的 ResNet18 候选 | 38/56 = 67.86% | 44.7 MB | 15.89 ms/张 |
| EfficientNet-B0 候选 | 41/56 = 73.21% | 16.0 MB | 12.74 ms/张 |

两款模型都使用同一组照片、同一 ONNX Runtime CPU 和相同的 56 张；计时仅为本机推理，不包括上传、网络往返和服务排队。ONNX 与 PyTorch 输出最大 logit 差 `1.431e-5`，预测一致。

## 决定

EfficientNet-B0 在本轮探索中更小、更快，固定留出结果也提高了 3/56 张，但仍为 `41/56`，低于 75% 门槛。样本集不独立，之前的模型实验已经反复使用这些图。故候选模型只保存在本机 `data/recognition-efficientnet-b0-20261021/model.onnx`，不会替换正式 ResNet18，也不启用自动识别；正式 `readyForDemo` 仍为 false，继续保留手动选择 fallback。

下一步需用按地点/个体隔离的新湛江现场照片做盲测。若模型在新现场数据上稳定超过门槛，再比较真实手机到卡片显示的端到端时延后决定是否上线。

复现命令：

```powershell
.\.venv\Scripts\python.exe tools\tune_efficientnet_b0.py
```

明细见 `data/recognition-efficientnet-b0-20261021/comparison.json`。ONNX 文件被 Git 忽略；脚本可从 torchvision 的 ImageNet 预训练权重重建。
