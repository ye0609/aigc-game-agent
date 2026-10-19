# 物种图片来源

`species/` 中的四张图片用于物种详情展示，均从 `data/recognition/sources.csv` 登记的 iNaturalist 照片复制。2026-10-19 再次通过 iNaturalist 观察 API 核对了照片 ID、物种名和逐张照片的 `cc0` 许可。图片并非湛江现场拍摄，不应标注为当地实拍；后续若替换为现场照片，应同步更新来源和许可记录。

| 展示文件 | 原始文件 | 摄影者 | iNaturalist 观察 ID | 照片 ID | 许可 |
| --- | --- | --- | --- | --- | --- |
| `species/mangrove-aegiceras-corniculatum/main.jpg` | `data/recognition/mangrove-aegiceras-corniculatum/IMG_0001.jpg` | Tim Shields | [409056593](https://www.inaturalist.org/observations/409056593) | 752035599 | CC0 |
| `species/mangrove-avicennia-marina/main.jpg` | `data/recognition/mangrove-avicennia-marina/IMG_0022.jpg` | Stuart | [393741693](https://www.inaturalist.org/observations/393741693) | 721741508 | CC0 |
| `species/mangrove-bruguiera-gymnorrhiza/main.jpg` | `data/recognition/mangrove-bruguiera-gymnorrhiza/IMG_0018.jpg` | Ellyne Geurts | [365071824](https://www.inaturalist.org/observations/365071824) | 666500329 | CC0 |
| `species/mangrove-kandelia-obovata/main.jpg` | `data/recognition/mangrove-kandelia-obovata/IMG_0020.jpg` | Scott Edmunds | [293352431](https://www.inaturalist.org/observations/293352431) | 527993466 | CC0 |

照片的原始 URL、许可证和 SHA-256 见 `data/recognition/sources.csv`。`assets/audio/` 尚未交付，前端音频将使用已有的语音兜底逻辑。
