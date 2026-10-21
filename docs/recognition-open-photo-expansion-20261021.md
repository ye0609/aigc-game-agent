# 开放许可照片扩充与训练

日期：2026-10-21。新增照片来自 iNaturalist 的研究级观察记录，仅接收 `CC0`、`CC BY`、`CC BY-SA`。每条记录保留作者、许可证、观察页、照片页、观察 ID、摄影者 ID、坐标、日期和 SHA-256。图片保存在本机且由 `.gitignore` 排除；仓库只追踪来源及筛选清单、训练脚本和指标。

## 新增数据

本批检索覆盖中国、香港、台湾索引，之后再补全球公开记录；全球补充时排除坐标仍落在中国检索范围内的重复记录。每个 iNaturalist observation 最多取一张照片。同一观察 ID 只是拍摄场次近似组，不能证明是不同树。

| 物种 | 下载候选 | 人工筛查后保留 | 观察组 | 摄影者 |
| --- | ---: | ---: | ---: | ---: |
| 桐花树 `mangrove-aegiceras-corniculatum` | 60 | 59 | 59 | 36 |
| 白骨壤 `mangrove-avicennia-marina` | 60 | 58 | 58 | 33 |
| 木榄 `mangrove-bruguiera-gymnorrhiza` | 60 | 60 | 60 | 35 |
| 秋茄 `mangrove-kandelia-obovata` | 47 | 43 | 43 | 20 |
| **合计** | **227** | **220** | **220** | — |

秋茄检索最终只有 47 张符合许可、去重和研究级条件的照片；没有用来源不明图片补到 60。缩略图人工初筛排除 7 张：桐花树 1 张、白骨壤 2 张、秋茄 4 张。理由见 `data/recognition-balance-20261021/excluded.csv`；实际训练清单为 `curated.csv`。联系表为本地审阅用，不上传图片。

## 来源与归属

照片的公开页及逐张归属都在 `data/recognition-balance-20261021/sources.csv`，保留的 220 张在 `curated.csv`。许可分布：桐花树 45 张 CC BY、9 张 CC0、5 张 CC BY-SA；白骨壤 43 张 CC BY、10 张 CC0、5 张 CC BY-SA；木榄 51 张 CC BY、7 张 CC0、2 张 CC BY-SA；秋茄 27 张 CC BY、15 张 CC0、1 张 CC BY-SA。使用照片或重新分发时须按对应许可提供署名；CC BY-SA 内容还要遵循相同方式共享要求。请通过来源清单逐项署名，不要只把本段当作图片署名。

## 训练与验证设计

训练整合三份照片来源：原始四类训练集 147 张、中国观察组精选集 147 张、本次筛查后新增 220 张，共 514 张。脚本会逐张验证文件哈希、来源清单和许可，并拒绝重复图片内容。

开发集仅从本次新增批次中、且摄影者 ID 不在此前两份数据来源中的作者组选取。一个作者的照片不会跨训练集和开发集。这样可避免用旧的 56 张探索性留出集继续调参；这些旧照片不再用于本轮开发结果。训练使用 ImageNet 预训练 ResNet18，微调最后一层卷积块和分类头，并按训练集类别频数加权。该划分仍是网上照片的作者隔离开发集，不能代替湛江新地点、新个体的现场盲测。

## 本轮结果

训练 485 张，开发集 29 张，来自 5 位历史来源中没有出现过的摄影者：正确 28 张，准确率 96.55%；宏平均召回率 96.88%。白骨壤召回率 87.5%（7/8），其余三类在当前小型开发集均为 100%。唯一错误是白骨壤判成桐花树。ONNX 与 PyTorch 预测一致，最大 logit 差 `3.81e-6`；本机 ONNX Runtime CPU 测试平均约 14.85 ms/张，模型约 44.7 MB。详细混淆矩阵和模型哈希见 `data/recognition-balance-20261021/expanded-resnet18-metrics.json`。

29 张、5 位摄影者仍是很小的线上照片开发集，96.55% 不能解释成真实场景准确率，也不能与之前的 56 张留出结果直接横比。它说明新增许可照片让候选模型在当前作者隔离样本上表现很好。

用户决定直接用于本地演示。候选 ONNX 已复制到本机 `backend/recognition/artifacts/model.onnx`，配套部署指标启用 `readyForDemo: true`；服务因此开启四类红树自动识别，低置信度与鸟类识别仍进入手动选择 fallback。此决定仅表示本机演示启用，不等于湛江现场验收。照片和模型都被 Git 忽略，其他机器需按下述步骤恢复数据、重训和激活。上线前仍需用湛江现场、按地点和树个体隔离的新照片盲测，并实测端到端延迟。

运行命令：

```powershell
.\.venv\Scripts\python.exe tools\collect_balance_photos.py --target-per-class 60 --max-per-author 15 --existing-root data\recognition --existing-root data\recognition-expansion-20261020b --existing-root data\recognition-china-groups-20261021 --existing-root data\recognition-china-curated-20261021
.\.venv\Scripts\python.exe tools\collect_balance_photos.py --restore
.\.venv\Scripts\python.exe tools\train_expanded_resnet18.py
.\.venv\Scripts\python.exe tools\activate_expanded_model.py --local-demo
```

重新克隆仓库后，应先从各自来源清单恢复旧训练图片，再恢复本批图片：

```powershell
.\.venv\Scripts\python.exe tools\collect_training_images.py --root data\recognition --restore
.\.venv\Scripts\python.exe tools\collect_training_images.py --root data\recognition-china-curated-20261021 --restore
.\.venv\Scripts\python.exe tools\collect_balance_photos.py --restore
```

候选模型和原始实验指标保存在本地 `data/recognition-balance-20261021/`。部署指标单独保存在被 Git 忽略的 `backend/recognition/artifacts/metrics.json`，标明这是用户批准的本地演示启用；原始实验指标的 `readyForDemo` 保持 false。后端仍以部署指标、模型 SHA-256、物种目录一致性决定是否加载，fallback 保留。
