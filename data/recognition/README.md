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

训练前必须为每张图片登记采集组。模板是 `data/recognition/groups.csv`，格式如下：

```csv
image,group_id
mangrove-bruguiera-gymnorrhiza/IMG_0001.jpg,mangrove-bruguiera-tree-01
mangrove-bruguiera-gymnorrhiza/IMG_0002.jpg,mangrove-bruguiera-tree-01
mangrove-bruguiera-gymnorrhiza/IMG_0003.jpg,mangrove-bruguiera-tree-02
```

同一棵树的照片（包括不同时间拍摄的照片）必须使用同一个 `group_id`；同一组连拍也必须归在一起。`group_id` 在整个数据集中必须唯一，建议带上物种前缀。每类至少需要两个不同采集组。训练脚本会把完整采集组分配到训练集或验证集，不会把一组照片拆开；验证样本量会因此略有浮动。`group_id` 不要包含姓名、电话或精确定位等隐私信息。

当前 4 类是初版候选物种；C 需在录入和采图前确认项目现场确实展示这 4 类。若更换物种，先同步更新 `data/species.catalog.json`、`docs/api.md` 和 mock，再开始训练。

## 当前公开许可数据集

仓库中的 `sources.csv` 是由 `tools/collect_training_images.py` 生成的来源清单。当前 147 张图片来自 iNaturalist 的研究级观察，逐张照片的许可证为 `CC BY`、`CC0` 或 `CC BY-SA`，并记录了观察页、作者、许可证、观察 ID 和 SHA-256。`groups.csv` 使用 iNaturalist observation ID 作为采集组；同一次观察只取一张照片，避免连拍图片同时进入训练集和验证集。

这批公开图片用于验证训练管线和接口，不等于湛江现场数据。运行基线训练后如果 `validationAccuracy` 低于 0.75，必须保留 `readyForDemo: false`，演示继续使用手动选物种 / GPS 点位兜底。后续加入湛江实拍时，应在 `sources.csv` 中记录来源，并把同一棵树或同一次采集的图片改成同一个真实 `group_id`；不能把不同来源的图片伪装成同一采集组。

重新获取同样规则的数据：

```bash
python tools/collect_training_images.py
```

该脚本不会把图片提交到 GitHub（训练图片目录由 `.gitignore` 忽略），但 `groups.csv` 和 `sources.csv` 应随数据版本一起保存。

训练前先运行：

```bash
python backend/recognition/dataset.py --root data/recognition --min-per-class 30
```

训练图片较大且仓库已忽略 `data/recognition/<speciesId>/` 下的图片，C 和 B 需要在正式采集前约定一个共享云盘目录或对象存储位置。C 按上述目录结构放图片，并提交更新后的 `groups.csv`；B 从约定位置同步图片到本地训练目录。不要把含个人信息的采集记录或私有访问链接提交到 GitHub。
