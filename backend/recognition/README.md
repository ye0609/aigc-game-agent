# 红树识别初版

这里是第 2 周的可运行识别基线。它使用 Pillow 读取照片、numpy 提取颜色和低分辨率空间特征，再用每类中心做最近邻分类。它的价值是先得到可复现的训练流程、验证准确率和低置信度兜底信号；真实样本足够后，可以替换模型而不改变前端接口。

## 安装

```bash
python -m pip install -r backend/recognition/requirements.txt
```

## 检查数据集

```bash
python backend/recognition/dataset.py --root data/recognition --min-per-class 30
```

## 训练和评估

```bash
python backend/recognition/train.py --root data/recognition --min-per-class 30
```

训练需要 `data/recognition/groups.csv` 中每张图片的 `image,group_id` 映射；缺文件、漏图或任一类别少于两个独立采集组都会停止训练。切分按采集组完成，避免同一棵树的近似照片同时进入训练集和验证集。分组规则和模板见 `data/recognition/README.md`。

输出：

- `backend/recognition/artifacts/model.npz`：模型参数（本地生成，不提交）
- `backend/recognition/artifacts/metrics.json`：验证集样本数和准确率

`validationSplit` 应显示为 `grouped-by-group_id`。只有 `validationAccuracy >= 0.75` 才把 `readyForDemo` 写为 true；服务加载模型前还会读取同目录的 `metrics.json`，只有 `readyForDemo: true` 才会在 health 中报告模型就绪并执行识别。该基线和小样本评估不能代表现场准确率，仍需用独立地点和现场手机照片复测。

## 单张推理

```bash
python backend/recognition/infer.py path/to/photo.jpg
```

## 与 A 联调

```bash
python backend/recognition/api.py
```

接口仍是 `POST /api/recognition/species`。模型文件不存在或无法加载时，`GET /api/health` 会报告 `mangroveModelReady: false`；识别接口在模型不存在时返回 `fallbackRequired: true`、`speciesId: null`，让 A 展示手动选物种。鸟类模型还没有开发，同样返回兜底信号。其他路径目前仍由 mock 响应。

本机默认绑定 `127.0.0.1:8000`。供手机在局域网联调时，可设置 `HOST=0.0.0.0` 和仅用于开发的 `API_TOKEN`；非本机地址未设置 token 时服务会拒绝启动，设置后每个 GET/POST 都需要 `Authorization: Bearer <API_TOKEN>`。图片请求体上限为 15 MiB。不要将服务直接暴露到公网，也不要把 token 提交到仓库。

手机相机/GPS 联调优先使用同域 HTTPS 反向代理，由代理持有 token，后端仍监听 `127.0.0.1`；步骤与示例 Caddy 配置见 `docs/deployment.md`。前端代码不应保存 token。

`confidence` 在此基线中只是按类别距离差构造的启发式分数，不是经过校准的概率。它可用于触发兜底，不能当作真实识别准确率；真实准确率只看独立验证集和现场测试。

## 当前阻塞

仓库尚未收到 C 的 4 类训练照片，所以当前只能运行数据集检查和代码测试，不能报告真实识别率。C 提供图片后，把图片按 `data/recognition/README.md` 的目录放置，再运行上面的命令。
