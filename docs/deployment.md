# 手机联调与演示部署

## 推荐拓扑

手机浏览器只访问一个 HTTPS 地址：`https://<演示域名或局域网 IP>/`。同一地址的 `/api/*` 由反向代理转发到电脑本机的 `127.0.0.1:8000`，`/data/species/*` 和 `/data/sites.json` 仅提供页面实际使用的结构化 JSON；训练图片和 `sources.csv` 不经静态代理公开。`/assets/*` 提供 C 交付的图片与音频资源。代理从自己的环境变量读取 `API_TOKEN`，在转发时添加 `Authorization: Bearer ...`。前端使用相对地址 `/api`、`/data` 和 `/assets`，`index.html`、Git 提交和二维码中都不放 token。

`API_TOKEN` 只鉴别反向代理到后端的请求，不是手机用户的登录机制。局域网演示应使用可信 Wi-Fi 并在防火墙只开放 HTTPS 端口；如需限制谁能打开页面，还应在代理层另加访问控制。不要把后端的 8000 端口直接暴露给局域网或公网。

## 局域网联调（Windows PowerShell）

1. 在电脑上安装 Python 依赖和 Caddy，并确认手机与电脑在同一个可信局域网。
2. 在仓库根目录的 PowerShell 中设置环境变量，`DEMO_HOST` 改成电脑实际的局域网 IP：

   ```powershell
   python -m pip install -r backend/recognition/requirements.txt
   $bytes = New-Object byte[] 32
   [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
   $env:API_TOKEN = -join ($bytes | ForEach-Object { $_.ToString('x2') })
   $env:DEMO_HOST = '192.168.1.23' # 示例；替换为电脑实际局域网 IP
   $env:HOST = '127.0.0.1'
   $env:PORT = '8000'
   ```

3. 在**同一个 PowerShell** 中启动后端和代理，让两者继承同一个 token：

   ```powershell
   $backend = Start-Process -FilePath python -ArgumentList 'backend/recognition/api.py' -PassThru -WindowStyle Hidden
   try {
       caddy run --config docs/Caddyfile.lan.example --adapter caddyfile
   } finally {
       Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
   }
   ```

4. Caddy 的 `tls internal` 使用本地 CA。电脑和测试手机都必须信任该 CA 证书，且手机访问的 IP 必须与 `DEMO_HOST` 一致；仅打开一个不受信任证书的页面不足以完成相机/GPS 真机测试。先用电脑访问 `https://<DEMO_HOST>/api/health`，再用手机访问相同地址并允许相机、定位权限。

5. 检查 `/api/health`：`mangroveModelReady: false` 表示训练模型尚未就绪，此时拍照应进入手动选物种流程。断开代理或直接请求 `http://127.0.0.1:8000/api/health`（不带 token）应得到 401。前端和代理同域，不需要浏览器发送 `Authorization`。

局域网 IP 更换时，更新 `DEMO_HOST` 并重新签发/信任对应证书。训练图片和模型尚未到位时，不要把 mock 返回或手动选择称为真实识别准确率。

## 最终二维码部署

使用一个可从手机访问的 HTTPS 域名：代理同时提供 `frontend/` 静态页面和 `/api/*`，后端仍只监听 `127.0.0.1:8000`；把 `API_TOKEN` 放在服务器的进程环境或密钥管理器中，由代理添加请求头。使用受信任的正式 TLS 证书，不使用 `tls internal`。限制访问来源、设置日志与备份，再生成指向 HTTPS 首页的二维码。不能只把 `frontend/index.html` 放到静态托管平台，同时期待它的 `/api` 自动连到 B 的电脑。

## 当前接口限制

- `backend/recognition/api.py` 仅在四类红树 ONNX 模型及指标都达标时启用自动识别；模型不存在或未达标时返回 `fallbackRequired: true`。鸟类识别还没有真实模型。
- 问答、讲解、TTS 和上报目前仍复用 mock；TTS 返回 `audioUrl: null` 和 `fallbackRequired: true`，由浏览器语音兜底；上报没有持久化。它们可以用于接口联调，不能作为正式服务验收。
- `POST /api/reports` 要求有效经纬度。GPS 获取失败时，前端应请求重试或提供人工选点，不能提交缺失坐标或 `0,0`。
