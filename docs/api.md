# 接口契约 v1

状态：草案，周三对齐会后锁定。

## 通用约定

- Base URL：由部署环境提供，例如 `http://localhost:8000/api`
- 请求和返回均使用 `application/json`，图片上传接口使用 `multipart/form-data`
- 成功返回 HTTP 200；参数错误返回 400；未登录或无权限返回 401/403；请求体超过 15 MiB 返回 413；服务异常返回 500
- 每个响应包含 `requestId`，便于联调排查
- `POST /reports` 的 `observation.speciesId` 必须来自 `data/species.catalog.json` 中当前已接入识别的物种；尚未接入识别的本地展示物种不能上报
- TTS 的 `text` 最多 2000 个字符；超过上限返回 400
- 本机默认服务地址只监听 `127.0.0.1`。手机联调与二维码演示使用同域 HTTPS 反向代理：代理从环境变量读取 `API_TOKEN` 并添加 `Authorization: Bearer <API_TOKEN>`，后端仍监听本机，浏览器只请求 `/api`，不得在 `index.html` 中放 token。局域网直接调用后端时也可设置 `HOST=0.0.0.0` 和 `API_TOKEN`，但不得用于公开部署；具体配置见 `docs/deployment.md`

## 1. 物种识别

`POST /recognition/species`

请求：`multipart/form-data`

```text
image: 图片文件（必填）
latitude: number（可选）
longitude: number（可选）
mode: "mangrove" | "bird"（必填）
```

返回：

```json
{
  "requestId": "req_demo_001",
  "success": true,
  "data": {
    "speciesId": "mangrove-bruguiera-gymnorrhiza",
    "name": "木榄",
    "category": "mangrove",
    "confidence": 0.92,
    "alternatives": [],
    "fallbackRequired": false
  },
  "error": null
}
```

识别不确定时返回 `success: true`、`fallbackRequired: true`，前端展示手动选物种和 GPS 点位卡片。

模型未就绪时返回同一结构，但 `speciesId`、`name` 为 `null`，`confidence` 为 `0.0`；此时前端必须使用手动选择，不得把返回结果当成真实识别。

## 2. RAG 问答

`POST /knowledge/ask`

请求：

```json
{
  "question": "为什么红树林能防风浪？",
  "language": "zh-CN",
  "contextSpeciesId": "mangrove-bruguiera-gymnorrhiza"
}
```

返回：

```json
{
  "requestId": "req_demo_002",
  "success": true,
  "data": {
    "answer": "红树林的根系能够固定泥沙，并削弱风浪能量。",
    "sources": ["knowledge/mangrove-coast.md"]
  },
  "error": null
}
```

## 3. AI 讲解稿

`POST /knowledge/explain`

请求：

```json
{
  "speciesId": "mangrove-bruguiera-gymnorrhiza",
  "language": "zh-CN",
  "audience": "student"
}
```

返回：

```json
{
  "requestId": "req_demo_003",
  "success": true,
  "data": {
    "title": "认识木榄",
    "script": "木榄是红树林中的重要成员……",
    "durationSeconds": 45
  },
  "error": null
}
```

## 4. TTS 音频

`POST /audio/tts`

请求：

```json
{
  "text": "欢迎来到红树林。",
  "language": "zh-CN",
  "voice": "standard"
}
```

返回：

```json
{
  "requestId": "req_demo_004",
  "success": true,
  "data": {
    "audioUrl": null,
    "language": "zh-CN",
    "durationSeconds": 4,
    "fallbackRequired": true,
    "provider": "browser"
  },
  "error": null
}
```

支持语言：`zh-CN`、`zh-HK`、`en-US`；雷州话固定短语使用预录音频。mock 阶段没有真实音频 URL，返回 `audioUrl: null` 和 `fallbackRequired: true`，前端应使用浏览器语音；接入真实 TTS 后再返回 HTTPS 音频地址。

## 5. 观测 / 垃圾上报

`POST /reports`

请求：`multipart/form-data`

```text
type: "observation" | "litter"（必填）
speciesId: string（观测时必填）
latitude: number（必填）
longitude: number（必填）
note: string（可选）
image: 图片文件（可选）
```

返回：

```json
{
  "requestId": "req_demo_005",
  "success": true,
  "data": {
    "reportId": "report_demo_001",
    "status": "received"
  },
  "error": null
}
```
