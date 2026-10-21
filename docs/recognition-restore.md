# 本机演示一键恢复

目标：在一台只有仓库和 Python 的干净机器上，用**一条命令**完成依赖安装、模型校验、指标生成、服务启动和健康检查；模型缺失或哈希不符时直接失败，不静默降级。

## 1. 准备

- Python 3.11 或 3.12（Windows 用 `py -3.11` / `py -3.12` 均可）。
- 能访问 PyPI，或已经配置好公司/学校镜像。
- 一个与 `models/recognition/manifest.json` 匹配的 `model.onnx`。
- 仓库本身；不需要提交模型二进制。

## 2. 一条命令

```powershell
python tools/setup_local_demo.py --model D:\models\model.onnx
```

也可以直接给 HTTPS 地址：

```powershell
python tools/setup_local_demo.py --model https://your-bucket.example/model.onnx
```

成功后输出：

```json
{
  "apiPid": 12345,
  "demoPid": 12346,
  "apiPort": 8000,
  "demoPort": 5173,
  "url": "http://127.0.0.1:5173/",
  "modelVersion": "resnet18-expanded-onnx-v1",
  "modelSha256": "f01103b2ef2f4bb70c4ecce198c2849415a064de8c607c102c107631a7a070b9",
  "health": {
    "service": "hybrid",
    "status": "ok",
    "mangroveModelReady": true
  }
}
Local demo is ready.
```

退出码：

- `0`：服务已启动，`/api/health` 报告红树模型就绪。
- `1`：服务启动或健康检查失败（会打印 API/demo 日志尾部）。
- `2`：模型/清单/报告校验失败，或参数错误；不会启动半残服务。

## 3. 脚本实际做了什么

1. 读取 `models/recognition/manifest.json`，校验 `modelVersion`、`sha256`、`bytes`、`classes`。
2. 读取 `data/recognition-balance-20261021/expanded-resnet18-metrics.json`，确认：
   - `readyForDemo: false`（原始实验报告不得被改写）
   - `modelSha256` / `modelBytes` 与清单一致
   - `developmentAccuracy >= 0.75`、`developmentSamples >= 20`
   - 类别与 `data/species.catalog.json` 一致
3. 创建/复用 `.venv`，安装 `backend/recognition/requirements.txt`（numpy、Pillow、onnxruntime）。
4. 校验模型大小和 SHA-256；不符就退出 2。
5. 复制模型到 `backend/recognition/artifacts/model.onnx`，生成部署 `metrics.json`（`readyForDemo: true`，标注 `demoActivation: one-command-local-demo`）。
6. 用 `REQUIRE_MODEL=1` 启动 `backend/recognition/api.py`，再启动 `tools/serve_local_demo.py`。
7. 轮询 `http://127.0.0.1:5173/api/health`，确认 `mangroveModelReady: true` 后退出 0。

模型文件仍然不进 Git；仓库只保存版本、哈希、大小和恢复脚本。

## 4. 模型清单

`models/recognition/manifest.json`：

```json
{
  "schemaVersion": 1,
  "modelVersion": "resnet18-expanded-onnx-v1",
  "artifact": "model.onnx",
  "sha256": "f01103b2ef2f4bb70c4ecce198c2849415a064de8c607c102c107631a7a070b9",
  "bytes": 44704752,
  "downloadUrl": null,
  "report": "data/recognition-balance-20261021/expanded-resnet18-metrics.json",
  "validationScope": "local-demo-only",
  "fieldValidated": false,
  "classes": [
    "mangrove-aegiceras-corniculatum",
    "mangrove-avicennia-marina",
    "mangrove-bruguiera-gymnorrhiza",
    "mangrove-kandelia-obovata"
  ]
}
```

- `downloadUrl` 目前为 `null`：仓库里没有可公开下载的模型地址，必须用 `--model` 指定本地文件或 HTTPS 地址。
- 模型来源：训练机上的 `data/recognition-balance-20261021/resnet18-expanded-candidate.onnx`。
- 换模型时同时更新 `sha256`、`bytes`，并确认实验报告的 `modelSha256` / `modelBytes` 一致；否则脚本会拒绝。

## 5. 强制失败行为

模型缺失：

```text
ERROR: no model supplied and manifest downloadUrl is null.
Pass --model PATH_OR_URL. Expected SHA-256: f01103... (44704752 bytes).
```

哈希不符：

```text
ERROR: model SHA-256 mismatch: expected ..., got ...
```

API 在 `REQUIRE_MODEL=1` 下缺模型/哈希不符：

```text
FATAL: REQUIRE_MODEL=1 but model.onnx/metrics.json are missing or failed hash/format validation.
```

直接运行 `python backend/recognition/api.py` 仍保留原有 fallback 行为；一键恢复脚本强制使用 `REQUIRE_MODEL=1`，所以演示启动不会静默降级。

## 6. 干净目录验证记录

2026-10-21 在 `D:\longzaifei\clean-test`（从仓库复制、删除 `.venv`/artifacts、新建 venv）执行：

```powershell
python tools/setup_local_demo.py `
  --model D:\longzaifei\setup-fixture\model.onnx `
  --manifest D:\longzaifei\setup-fixture\manifest.json `
  --report D:\longzaifei\setup-fixture\report.json
```

结果：

- 新建 `.venv`，安装 numpy/Pillow/onnxruntime 成功。
- 模型大小/SHA-256 校验通过，服务启动成功。
- `http://127.0.0.1:5173/` → 200。
- `/api/health` → `mangroveModelReady: true`。
- 篡改模型字节后重新执行 → 退出 2，报 SHA-256 mismatch，未启动服务。
- 删除 `artifacts/model.onnx` 后直接 `REQUIRE_MODEL=1 python backend/recognition/api.py` → 退出 2，报 FATAL，未启动服务。

注意：这次用的是 **485 字节的 ONNX 测试夹具**，不是生产模型；它只验证“一条命令、哈希校验、启动、健康检查、硬失败”的机制。生产模型二进制仍只在训练机上，尚未进入本仓库或可下载地址。

## 7. 日志、停止、排错

- 日志：`.local-demo/api.log`、`.local-demo/demo.log`
- PID/URL/哈希：`.local-demo/pids.json`
- 停止：
  ```powershell
  $p = Get-Content .local-demo/pids.json | ConvertFrom-Json
  Stop-Process -Id $p.apiPid,$p.demoPid
  ```
- 端口占用：脚本会在启动前检查 8000/5173，被占用时退出 2；先停旧服务。
- 依赖安装失败：确认 Python 版本、pip 镜像、网络；可先手动 `python -m venv .venv` 后重试。
- 模型哈希不符：不要改清单迁就模型；用训练机上的候选文件，或重新导出并更新清单/报告。

## 8. 尚未覆盖

- 手机 HTTPS：需要隧道或反向代理，见 `docs/deployment.md`；一键脚本只绑定 `127.0.0.1`。
- 湛江现场准确率：28/29 是网络照片开发集；现场验收需要独立地点/个体、多机型、不同光照的 50 张盲测。
- TTS/RAG/上报/鸟类识别：仍为 mock/未完成。
