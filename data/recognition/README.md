# 识别训练集

训练图片按稳定的 `speciesId` 分目录，不按中文名分目录：

```text
data/recognition/
├─ mangrove-bruguiera-gymnorrhiza/
│  ├─ IMG_0001.jpg
│  └─ IMG_0002.jpg
├─ mangrove-kandelia-obovata/
├─ mangrove-aegiceras-corniculatum/
└─ mangrove-avicennia-marina/
```

第 2 周目标是每类 30～50 张，尽量覆盖正面、侧面、远景、不同光照和不同手机角度。文件名不要包含姓名、电话或定位隐私。

同一棵树连拍的近似照片不要同时分到训练集和验证集。尽量让验证集来自不同植株、采集时段或地点；当前基线按图片随机切分，样本有分组时应先整理并按组切分，避免验证准确率虚高。

当前 4 类是初版候选物种；C 需在录入和采图前确认项目现场确实展示这 4 类。若更换物种，先同步更新 `data/species.catalog.json`、`docs/api.md` 和 mock，再开始训练。

训练前先运行：

```bash
python backend/recognition/dataset.py --root data/recognition --min-per-class 30
```

当前仓库只提交目录说明，不提交训练照片；C 收集好图片后放入对应目录，或按同样结构提供压缩包。
