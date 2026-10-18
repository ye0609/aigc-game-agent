# Mock 服务

这里放第 1 周供前端联调的假接口和假数据。mock 的请求路径、字段名和返回结构必须与 `docs/api.md` 一致。

## 启动

本服务只使用 Python 标准库，不需要安装依赖：

```bash
cd backend/mock
python server.py
```

启动后访问 `http://127.0.0.1:8000/api/health` 检查服务状态。

## 联调示例

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

问答：

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"为什么红树林能防风浪？\",\"language\":\"zh-CN\"}"
```

识别（Windows PowerShell）：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/recognition/species `
  -F "mode=mangrove" -F "image=@木榄.jpg"
```

图片文件名包含“木榄”“秋茄”“桐花树”或“白骨壤”时，mock 会返回对应物种；其他图片返回默认物种。

## 自检

```bash
python -m unittest test_server.py -v
```

## 交付要求

- 覆盖红树、鸟类识别
- 覆盖 RAG 问答和 AI 讲解稿
- 覆盖普通话、粤语、英语 TTS 返回
- 覆盖观测 / 垃圾上报成功和失败场景
- 为每个接口提供至少一个可复制的请求示例
