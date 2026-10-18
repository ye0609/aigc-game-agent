# 数据字段模板

这些模板是 A、B、C 之间的共同输入输出格式。C 负责补齐真实内容，A 按字段渲染，B 使用 `speciesId` 作为识别和 RAG 的稳定主键。

- `species.schema.json`：物种数据字段约束
- `species.example.json`：一条完整物种记录示例
- `sites.schema.json`：地点、步道和观鸟屋字段约束
- `sites.example.json`：地点、步道和观鸟屋记录示例
- `species.catalog.json`：识别、前端和内容共用的稳定物种 ID 清单
- `species/`：4 种红树的完整内容，一条记录一个文件，文件名即 `speciesId`
- `recognition/`：按 `speciesId` 分目录的训练图片，见其中的 README

图片、音频使用相对路径或最终对象存储 URL；不要把密钥放在 JSON 中。

## 物种内容文件

`data/species/` 下每种红树一个 JSON，字段必须符合 `species.schema.json`，文件名与 `speciesId` 一致。当前 4 条：

- `mangrove-bruguiera-gymnorrhiza.json`：木榄
- `mangrove-kandelia-obovata.json`：秋茄
- `mangrove-aegiceras-corniculatum.json`：桐花树
- `mangrove-avicennia-marina.json`：白骨壤

`species.catalog.json` 是 A、B、C 共用的稳定 ID 清单。新增、改名或删除物种时，先改 catalog，再改内容文件；否则 `data/test_species_data.py` 会失败。

图片和音频路径是交付契约。当前仓库只保存路径，实拍图和录音文件就位后放到 `assets/` 或对象存储并替换 URL；不要把大文件、个人信息或未授权素材提交到仓库。

改动物种数据后运行：

```bash
python data/test_species_data.py -v
```
