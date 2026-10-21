# 红树林研学 App

面向红树林生态研学的 H5 应用，包含物种识别、地图点位、时间轴、图鉴、研学任务和蓝碳科普。

## 目录

- `frontend/`：H5 前端工程（A 负责）
- `backend/`：接口、模型、RAG、TTS 和 mock 服务（B 负责）
- `data/`：物种、地点、路线、题库等结构化数据（C 负责）
- `docs/`：接口契约、部署和联调说明

协作规则见 `CONTRIBUTING.md`；已经确认的跨成员决定见 `docs/decisions.md`。

## 协作约定

- `main`：可运行和可演示版本
- 功能开发使用 `feature/<name>` 分支
- 合并前补充 README 或接口变更说明
- API Key、密码、真实服务器配置不得提交到仓库
- 大型训练集和音视频素材放在约定的云盘或对象存储，仓库只保存索引和元数据

## 当前状态

当前进度：接口 mock、H5 页面和四类红树识别已具备本地演示能力。新增的许可照片扩充实验使用 485 张训练图，在 29 张按摄影者隔离的网络照片开发集上答对 28 张（96.55%）。用户已决定在本机演示中启用这个 ResNet18 候选；低置信度仍走手动选择 fallback。模型与部署指标保存在本地 `backend/recognition/artifacts/`，不随 Git 提交。该结果不是湛江现场准确率；正式验收仍需当地新地点/新个体照片、真实 TTS/RAG、路线 GPS 和部署证书。实验及复现见 `docs/recognition-open-photo-expansion-20261021.md`。

## 快速开始

### 启动接口

识别服务会复用 mock 的问答、讲解、TTS 和上报路由；同一时间只启动这一个服务：

```powershell
python backend/recognition/api.py
```

健康检查：`http://127.0.0.1:8000/api/health`。本机安装扩充模型后应返回 `mangroveModelReady: true`；模型缺失或校验失败时返回 false，拍照识别使用手动选择兜底。

### 打开前端

在第二个终端运行 `python tools/serve_local_demo.py`，然后打开 `http://127.0.0.1:5173/`。本地服务器将页面、结构化数据和 `/api` 放在同一来源，并且只绑定回环地址。相机、定位和手机联调请按 `docs/deployment.md` 使用 HTTPS 同域反向代理；不要把后端 8000 端口直接暴露给手机或公网。

### 检查当前数据和代码

```powershell
python tools/collect_training_images.py --restore
python backend/recognition/dataset.py --root data/recognition --min-per-class 30
python -m pip install -r backend/recognition/requirements-train.txt
python tools/train_expanded_resnet18.py
python tools/activate_expanded_model.py --local-demo
```

训练图片目录被 `.gitignore` 忽略；从 GitHub 新 clone 后按 `docs/recognition-open-photo-expansion-20261021.md` 的命令恢复三批图片、重训并运行 `tools/activate_expanded_model.py --local-demo`。模型及部署 `metrics.json` 也是本地产物。缺失时服务自动回到手动选择兜底。
