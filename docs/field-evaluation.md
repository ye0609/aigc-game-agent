# 湛江现场独立测试

当前 ResNet18 已获准用于**本机演示**，不是现场准确率验收。模型文件为 `data/recognition-balance-20261021/resnet18-expanded-candidate.onnx`（本机 Git 忽略文件）；部署副本为 `backend/recognition/artifacts/model.onnx`。两者预期大小都是 44,704,752 B，SHA-256 为 `f01103b2ef2f4bb70c4ecce198c2849415a064de8c607c102c107631a7a070b9`。别的机器需要从训练机安全传输该文件，核对大小和完整哈希，再运行 `python tools/activate_expanded_model.py --local-demo`。仓库本身不包含模型文件。

## 采集与隔离

- 四类红树各拍 30–40 张，按不同树、地点、叶片、根部、整株、角度和光照分组；其中每类 10–15 张留作独立测试，整棵树的照片不能跨训练和测试。
- 再拍 20–30 张**不属于这四类红树**的 unknown 照片，含其他植物、非植物和质量不佳的照片。给 unknown 标正确标签；它们只用于测误认和兜底，不参与四类 top-1 准确率分母。
- 测试照片在评估完成前不得用于训练、选模型或调置信度阈值；否则该批照片不再是独立验收集。
- 记录拍摄地点 `siteId` 与树/对象 `treeId`。现场照片、许可和位置隐私由采集者保管，不要直接推送到公开仓库。

用户提供的 `D:\longzaifei\field_shoot\checklist.md` 当前未在这台电脑上找到；请让采集者确认实际路径。此文档先作为仓库内的采集与评估约定。

## manifest 和运行

保存 UTF-8 CSV，至少包含以下列。`image` 可为相对 manifest 目录的路径，也可为绝对路径；`speciesId` 使用 `data/species.catalog.json` 中的四类 ID，非目标照片填 `unknown`。只评估 `split=test` 行。

```csv
image,speciesId,siteId,treeId,split
photos/site-a-tree-01-leaf.jpg,mangrove-kandelia-obovata,site-a,tree-01,test
photos/site-b-object-01.jpg,unknown,site-b,object-01,test
```

在仓库根目录启动 `python backend/recognition/api.py` 和 `python tools/serve_local_demo.py` 后运行：

```powershell
python tools/evaluate_field.py D:\longzaifei\field_shoot\manifest.csv --output D:\longzaifei\field_shoot\results.json
```

脚本逐张调用真实识别接口，输出四类照片的 top-1、分物种召回、总体与分物种 fallback 率、unknown 兜底/误接收率，以及原始 top-1 和最终决策两份混淆矩阵。脚本会检查 manifest 的字段、测试标记、图片存在与重复，但**无法自行证明**树与地点真的独立；采集者必须核对。每类样本量未达到预定 10–15 张或 unknown 少于 20 张时，报告仅作试运行，不作验收结论。
