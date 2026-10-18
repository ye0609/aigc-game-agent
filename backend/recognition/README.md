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

输出：

- `backend/recognition/artifacts/model.npz`：模型参数（本地生成，不提交）
- `backend/recognition/artifacts/metrics.json`：验证集样本数和准确率

只有 `validationAccuracy >= 0.75` 才把 `readyForDemo` 视为 true；真实上线阈值还要用现场手机照片复测。

## 单张推理

```bash
python backend/recognition/infer.py path/to/photo.jpg
```

## 与 A 联调

```bash
python backend/recognition/api.py
```

接口仍是 `POST /api/recognition/species`。模型文件不存在时返回 `fallbackRequired: true`、`speciesId: null`，让 A 展示手动选物种；模型就绪后自动使用真实推理。鸟类模型还没有开发，同样返回兜底信号。其他路径目前仍由 mock 响应，`GET /api/health` 会报告每类模型的状态。

`confidence` 在此基线中只是按类别距离差构造的启发式分数，不是经过校准的概率。它可用于触发兜底，不能当作真实识别准确率；真实准确率只看独立验证集和现场测试。

## 当前阻塞

仓库尚未收到 C 的 4 类训练照片，所以当前只能运行数据集检查和代码测试，不能报告真实识别率。C 提供图片后，把图片按 `data/recognition/README.md` 的目录放置，再运行上面的命令。
