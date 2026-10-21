# 红树识别

当前默认服务检查 ResNet18 ONNX 模型及配套部署指标。用户已批准本地演示启用扩充照片训练的候选：网络照片作者隔离开发集 28/29（96.55%），模型和部署指标在本机 `artifacts/`，不会随 Git 提交。低置信度继续手动选择兜底，鸟类仍无真实模型。此结果不代表湛江现场识别表现；详见 `docs/recognition-open-photo-expansion-20261021.md`。原 centroid 训练仅保留作基线对照。

## 安装

```bash
python -m pip install -r backend/recognition/requirements.txt
```

训练环境建议使用 Python 3.11。训练时另装 PyTorch、torchvision 和 ONNX：

```bash
python -m pip install -r backend/recognition/requirements-train.txt
```

部署端只需上面的服务依赖，不需要安装 PyTorch。

## 检查数据集

```bash
python backend/recognition/dataset.py --root data/recognition --min-per-class 30
```

## ResNet18 训练、导出与评估

```bash
python backend/recognition/train_resnet18.py --root data/recognition --min-per-class 30
```

脚本固定按 `groups.csv` 隔离训练/验证图片，使用 ImageNet 预训练 ResNet18 提取特征、训练四分类头、导出 ONNX，并对同一验证集逐张核对 PyTorch 与 ONNX 输出。训练只读训练组，验证组不参与拟合；`readyForDemo` 仅在 ONNX 验证准确率至少 0.75 且导出一致性检查通过时为 true。输出为 `artifacts/model.onnx` 和 `artifacts/metrics.json`。模型本体未纳入 Git，交付时必须一并传递模型、指标文件和 SHA-256；否则后端会保持 fallback。

一次 28 张图片的分组验证只能说明当前公开照片的测试表现，不能替代湛江现场真机测试；非红树、模糊图和未知种也需要单独测试。softmax `confidence` 未校准，不应当作真实概率。

## 原 centroid 基线（对照）

```bash
python backend/recognition/train.py --root data/recognition --min-per-class 30 --output backend/recognition/artifacts/baseline.npz
```

训练需要 `data/recognition/groups.csv` 中每张图片的 `image,group_id` 映射；缺文件、漏图或任一类别少于两个独立采集组都会停止训练。切分按采集组完成，避免同一棵树的近似照片同时进入训练集和验证集。分组规则和模板见 `data/recognition/README.md`。

输出：

- `backend/recognition/artifacts/baseline.npz`：基线模型参数（本地生成，不提交）
- `backend/recognition/artifacts/baseline.metrics.json`：基线验证结果；不会覆盖 ONNX 模型的 `metrics.json`

旧版模型的 `validationSplit` 为 `grouped-by-group_id`，扩充候选的部署指标为 `new-batch-photographer-holdout-no-historical-author-overlap`。服务加载默认 ONNX 模型前会校验模型版本、验证划分、`readyForDemo: true`、`validationAccuracy >= 0.75`、模型 SHA-256 和四类物种目录一致性。基线和小样本评估都不能代表现场准确率，仍需用独立地点和现场手机照片复测。

## 单张推理

此命令仅用于本地诊断，会直接读取模型；演示是否启用自动识别仍以 `/api/health` 的 `mangroveModelReady` 为准。

```bash
python backend/recognition/infer.py path/to/photo.jpg
```

## 与 A 联调

```bash
python backend/recognition/api.py
```

接口仍是 `POST /api/recognition/species`。模型文件不存在或无法加载时，`GET /api/health` 会报告 `mangroveModelReady: false`；识别接口在模型不存在时返回 `fallbackRequired: true`、`speciesId: null`，让 A 展示手动选物种。鸟类模型还没有开发，同样返回兜底信号。其他路径目前仍由 mock 响应。

本机默认绑定 `127.0.0.1:8000`。供手机在局域网联调时，可设置 `HOST=0.0.0.0` 和仅用于开发的 `API_TOKEN`；非本机地址未设置 token 时服务会拒绝启动，设置后每个 GET/POST 都需要 `Authorization: Bearer <API_TOKEN>`。图片请求体上限为 15 MiB，TTS 文本最多 2000 个字符。跨域开发服务器需额外设置 `CORS_ORIGIN` 白名单；同域 HTTPS 代理不需要 CORS。不要将服务直接暴露到公网，也不要把 token 提交到仓库。

手机相机/GPS 联调优先使用同域 HTTPS 反向代理，由代理持有 token，后端仍监听 `127.0.0.1`；步骤与示例 Caddy 配置见 `docs/deployment.md`。前端代码不应保存 token。

`confidence` 不是经过校准的概率。它可用于触发兜底，不能当作真实识别准确率；真实准确率只看独立验证集和现场测试。

## 当前状态

本机已安装扩充候选 ONNX 和对应部署指标。复现时先按 `docs/recognition-open-photo-expansion-20261021.md` 恢复三批许可照片，再运行 `tools/train_expanded_resnet18.py` 与 `tools/activate_expanded_model.py --local-demo`。`GET /api/health` 应返回 `mangroveModelReady: true`；无本地模型文件时仍返回 false 并走手动选择。现场验收尚未完成，前端对未知种和低置信度结果仍需允许手动纠正。
