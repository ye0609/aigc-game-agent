# 第二批红树照片扩充实验

日期：2026-10-20。第二批从 iNaturalist 研究级观察中采集照片，只接受 `CC0`、`CC BY` 和 `CC BY-SA`。采集器按摄影者限额、观察 ID 和 SHA-256 去重，并将来源清单逐张写入临时目录。

## 采集结果

- 秋茄（`Kandelia obovata`）：50 张。
- 白骨壤（`Avicennia marina`）：4 张。接口前段结果与已有清单重合较多，采集在取得少量新增样本后停止。
- 与原 147 张及第一批 90 张清单合并后，111 张照片符合实验的新增条件；12 张超过摄影者上限，19 张来自固定验证摄影者，2 张视觉上缺少可用主体而排除。
- 缩略图抽查后，未将临时照片复制到正式 `data/recognition`，也没有替换 `backend/recognition/artifacts`。

## 固定验证集结果

两次训练使用相同的 29 张、按摄影者隔离的验证集和相同 ResNet18 冻结主干配方：

| 数据 | 训练样本 | 验证正确/总数 | 准确率 |
| --- | ---: | ---: | ---: |
| 原 147 张 | 118 | 20/29 | 0.6897 |
| 加第一批 67 张 | 185 | 21/29 | 0.7241 |
| 再加入本批可用照片（累计 178 张新增） | 229 | 21/29 | 0.7241 |

本批没有改善固定验证集，不能把准确率写成达到 `0.75`。正式模型的 `readyForDemo` 继续为 `false`，线上继续使用手动选择 fallback。

## 结论

当前主要混淆仍是秋茄与白骨壤。下一批照片应优先来自湛江演示地点的多棵树和多个地点，覆盖叶片近景、树干/根部、整株、花果或胚轴、逆光和遮挡；同时留出独立地点照片作最终验收。采集器和多批评估支持：

```powershell
.\.venv\Scripts\python.exe tools\collect_incremental_photos.py --root <临时目录> --existing-root data\recognition --existing-root data\recognition-expansion-20261020 --species mangrove-kandelia-obovata --target-per-class 50
.\.venv\Scripts\python.exe tools\evaluate_photo_expansion.py --extra-root data\recognition-expansion-20261020 --extra-root <临时目录>
```
