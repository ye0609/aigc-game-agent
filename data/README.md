# 数据字段模板

这些模板是 A、B、C 之间的共同输入输出格式。C 负责补齐真实内容，A 按字段渲染，B 使用 `speciesId` 作为识别和 RAG 的稳定主键。

- `species.schema.json`：物种数据字段约束
- `species.example.json`：一条完整物种记录示例
- `sites.schema.json`：地点、步道和观鸟屋字段约束
- `sites.example.json`：地点、步道和观鸟屋记录示例
- `species.catalog.json`：识别、前端和内容共用的稳定物种 ID 清单
- `recognition/`：按 `speciesId` 分目录的训练图片，见其中的 README

图片、音频使用相对路径或最终对象存储 URL；不要把密钥放在 JSON 中。
