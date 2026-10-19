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

当前进度：接口 mock、协作规则、红树识别数据集清单和基线评估已完成。仓库登记了 147 张公开许可图片的来源，但图片本体在本地或共享存储中，不提交 GitHub；当前基线验证准确率低于演示门槛，前端保留手动选择和地图模拟到点。正式验收仍需湛江现场照片、真实 TTS/RAG、路线 GPS 和部署证书。

## 快速开始

### 启动接口

识别服务会复用 mock 的问答、讲解、TTS 和上报路由；同一时间只启动这一个服务：

```powershell
python backend/recognition/api.py
```

健康检查：`http://127.0.0.1:8000/api/health`。没有达到 `readyForDemo` 的模型时，健康检查会明确返回 `mangroveModelReady: false`，拍照识别应使用手动选择兜底。

### 打开前端

本机可以直接打开 `frontend/index.html`，此时页面把接口请求发到 `http://127.0.0.1:8000/api`。相机、定位和手机联调请按 `docs/deployment.md` 使用 HTTPS 同域反向代理；不要把后端 8000 端口直接暴露给手机或公网。

### 检查当前数据和代码

```powershell
python tools/collect_training_images.py --restore
python backend/recognition/dataset.py --root data/recognition --min-per-class 30
python backend/recognition/train.py --root data/recognition --min-per-class 30
```

训练图片目录被 `.gitignore` 忽略，脚本默认只校验来源清单和 SHA-256；从 GitHub 新 clone 后用 `--restore` 下载清单中的缺失图片。当前基线准确率低于 0.75，训练会把模型标为未达到演示就绪条件。
