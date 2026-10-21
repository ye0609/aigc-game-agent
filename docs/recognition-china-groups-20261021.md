# 中国范围红树观察组扩充

日期：2026-10-21。按用户要求，将 iNaturalist 研究级观察作为“一棵树一组”的近似采集组：同一个 observation ID 的照片保持在同一组，组内最多 8 张，只接受 `CC0`、`CC BY`、`CC BY-SA`。观察记录包含坐标、作者、观察页、许可证和 SHA-256。

## 筛选结果

公开记录从 iNaturalist 的中国大陆、香港、台湾三个地点索引检索，再按坐标筛选；两类分别找到 252、236 条含开放许可证照片的研究级观察。满足每组至少 4 张且通过画面筛查的最终照片只来自台湾本岛和金门；大陆及香港缺少足够的合规多角度组：

- 原始下载：193 张，40 个观察组。
- 人工缩略图筛查后：147 张，30 个观察组。
- 秋茄 `Kandelia obovata`：74 张，17 组。
- 白骨壤 `Avicennia marina`：73 张，13 组。
- 每组至少 4 张，最多 8 张；最终许可证为 98 张 CC0、49 张 CC BY。
- 清除落叶、泥滩/水面、重复图像、只有根部或主体过远的照片 46 张。

原始清单在 `data/recognition-china-groups-20261021/`，训练用清单在 `data/recognition-china-curated-20261021/`。照片文件遵循仓库的大文件忽略规则，来源清单可根据 URL 恢复照片。

## 组留出实验

保留 5 个未参与训练的中国观察组（秋茄 3 组、白骨壤 2 组），共 25 张作地点/观察组留出；原有照片另按摄影者留出 31 张。结果：

| 模型 | 原有摄影者留出 | 中国观察组留出 |
| --- | ---: | ---: |
| 原 147 张 | 17/31 = 0.5484 | 12/25 = 0.4800 |
| 加入中国组后 | 17/31 = 0.5484 | 21/25 = 0.8400 |

这 31 张原有验证图片是本实验重新锁定的摄影者划分，不能与前一实验的 29 张验证集直接比较。扩充模型使用 238 张训练图片，留出图片共 56 张。

扩充模型的综合验证为 `38/56 = 0.6786`，仍低于 `0.75`。候选 ONNX、指标和比较结果保存在本机 `data/recognition-china-experiment-20261021/`；模型文件不提交到 Git，脚本可重训生成。

中国观察组测试只代表当前公开记录分布，样本数少，而且秋茄 74 张中 70 张由同一摄影者拍摄。观察 ID 只是采集场次，不能证明每组是一棵不同的树，也不能替代湛江现场独立采样。因此没有替换正式 `backend/recognition/artifacts/`，`readyForDemo` 仍由正式模型指标控制，fallback 继续保留。

## 复现

```powershell
.\.venv\Scripts\python.exe tools\inventory_observation_groups.py
.\.venv\Scripts\python.exe tools\collect_china_observation_groups.py --existing-root data\recognition --existing-root data\recognition-expansion-20261020 --existing-root data\recognition-expansion-20261020b
.\.venv\Scripts\python.exe tools\curate_china_observation_groups.py
.\.venv\Scripts\python.exe tools\evaluate_china_groups.py
```
