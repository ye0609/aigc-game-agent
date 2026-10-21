"""零依赖联调 mock 服务。

启动：python server.py
默认地址：http://127.0.0.1:8000
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import os
import re
import uuid
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 8000
MAX_REQUEST_BYTES = 15 * 1024 * 1024
MAX_TTS_TEXT_LENGTH = 2000
KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
QUESTION_STOPWORDS = {"什么", "为什么", "怎么", "如何", "可以", "哪些", "是否", "一个", "这个", "那个", "红树"}
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
ALNUM_RE = re.compile(r"[a-zA-Z0-9]{2,}")


def _load_knowledge_chunks() -> list[dict]:
    chunks = []
    if not KNOWLEDGE_DIR.is_dir():
        return chunks
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for block in re.split(r"\n\s*\n", text):
            block = " ".join(block.split())
            if len(block) < 24:
                continue
            chunks.append({"text": block, "source": f"knowledge/{path.name}"})
    return chunks


KNOWLEDGE_CHUNKS = _load_knowledge_chunks()


def _tokens(text: str) -> list[str]:
    text = text.lower()
    tokens = []
    for run in CJK_RE.findall(text):
        for size in (2, 3):
            for index in range(len(run) - size + 1):
                token = run[index:index + size]
                if token not in QUESTION_STOPWORDS:
                    tokens.append(token)
    tokens.extend(ALNUM_RE.findall(text))
    return tokens


def _score_question(question: str, text: str) -> float:
    question_tokens = set(_tokens(question))
    if not question_tokens:
        return 0.0
    text_tokens = _tokens(text)
    counts = {}
    for token in text_tokens:
        counts[token] = counts.get(token, 0) + 1
    score = sum(counts.get(token, 0) for token in question_tokens)
    return score / math.sqrt(max(len(text_tokens), 1))


def answer_question(question: str) -> dict:
    q = question.strip()
    if not q:
        return {"answer": "请先输入一个关于红树林、蓝碳或观鸟的问题。", "sources": []}
    if ("红树" in q) and any(word in q for word in ("几种", "多少种", "种类", "哪些")):
        return {
            "answer": "本项目重点收录 4 种红树：木榄、秋茄、桐花树、白骨壤。它们是湛江研学中最常见的代表种，但不是湛江红树林的全部；实际种类以保护区官方名录为准。",
            "sources": ["knowledge/mangrove-species.md"],
        }
    if any(word in q for word in ("防风", "风浪", "护岸", "海岸防护", "消浪")):
        return {
            "answer": "红树林的支柱根、呼吸根和密集茎干会增加水流阻力，削弱波浪能量；根系同时固定泥沙、减少岸滩侵蚀。它是天然海岸屏障，但不能替代海堤等工程设施，台风和大潮期间仍要遵守保护区安全规定。",
            "sources": ["knowledge/ecosystem.md"],
        }
    if any(word in q for word in ("蓝碳", "固碳", "碳汇", "碳库", "碳储量")):
        return {
            "answer": "蓝碳是由红树林、盐沼和海草床等海岸带生态系统固定的碳。红树林把碳储存在生物量和沉积物中，单位面积碳储量通常较高，但具体比例随地点、潮位和人类活动变化，不能用一个数字代表所有红树林。",
            "sources": ["knowledge/blue-carbon.md"],
        }
    if any(word in q for word in ("黑脸琵鹭", "白鹭", "勺嘴鹬", "观鸟", "鸟类")):
        return {
            "answer": "湛江红树林可见白鹭、黑脸琵鹭、勺嘴鹬等候鸟。黑脸琵鹭是国家一级保护野生动物；勺嘴鹬极度濒危。观鸟时保持距离，不投喂、不驱赶、不播放鸟鸣引诱，具体保护等级以官方名录为准。",
            "sources": ["knowledge/birds.md"],
        }
    if any(word in q for word in ("路线", "怎么去", "地图", "点位", "观鸟屋", "导航")):
        return {
            "answer": "项目包含高桥、特呈岛、金牛岛三个点位，仓库里的路线和观鸟屋是 WGS-84 参考坐标，尚未逐点实测。前端地图是示意底图，导航前要用手机 GPS 校准，并听从保护区向导安排。",
            "sources": ["knowledge/visiting.md"],
        }
    if any(word in q for word in ("安全", "注意", "礼仪", "潮汐", "泥滩")):
        return {
            "answer": "红树林研学要关注潮汐：退潮可观察呼吸根和底栖生物，但泥滩湿滑，不要单独进入；涨潮时不要停留在低滩。不采摘、不捕捉、不投喂，垃圾带走，台风或雷雨天气不要下滩。",
            "sources": ["knowledge/visiting.md"],
        }
    scored = sorted(
        ((_score_question(q, chunk["text"]), chunk) for chunk in KNOWLEDGE_CHUNKS),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] < 1.0:
        return {"answer": "当前知识库没有收录这个问题的可靠资料。可以换一种问法，或询问红树物种、生态功能、蓝碳、鸟类和研学点位。", "sources": []}
    best = scored[0][1]["text"].lstrip("# ").strip()
    return {"answer": best, "sources": [scored[0][1]["source"]]}


class RequestTooLargeError(Exception):
    pass

MANGROVES = {
    "木榄": {
        "speciesId": "mangrove-bruguiera-gymnorrhiza",
        "name": "木榄",
        "confidence": 0.92,
    },
    "秋茄": {
        "speciesId": "mangrove-kandelia-obovata",
        "name": "秋茄",
        "confidence": 0.89,
    },
    "桐花树": {
        "speciesId": "mangrove-aegiceras-corniculatum",
        "name": "桐花树",
        "confidence": 0.87,
    },
    "白骨壤": {
        "speciesId": "mangrove-avicennia-marina",
        "name": "白骨壤",
        "confidence": 0.91,
    },
}

BIRDS = {
    "白鹭": {"speciesId": "bird-egretta-garzetta", "name": "白鹭", "confidence": 0.86},
    "黑脸琵鹭": {"speciesId": "bird-black-faced-spoonbill", "name": "黑脸琵鹭", "confidence": 0.83},
}
VALID_REPORT_SPECIES = {item["speciesId"] for item in (*MANGROVES.values(), *BIRDS.values())}


def request_id() -> str:
    return f"req_{uuid.uuid4().hex[:10]}"


def response(data=None, error=None, status=200):
    return status, {"requestId": request_id(), "success": error is None, "data": data, "error": error}


def error(message: str, status: int = 400):
    return response(error={"code": "INVALID_REQUEST", "message": message}, status=status)


def parse_json(raw: bytes):
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("请求体必须是合法 JSON")
    if not isinstance(value, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return value


def parse_multipart(raw: bytes, content_type: str):
    # email parser 可处理 boundary、文件名和字段编码，避免手写边界切分。
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw
    )
    fields = {}
    files = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = {"filename": filename, "size": len(payload), "content": payload}
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    fields["_files"] = files
    return fields


def parse_body(handler: BaseHTTPRequestHandler):
    if handler.headers.get("Transfer-Encoding"):
        raise ValueError("不支持 Transfer-Encoding")
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ValueError("Content-Length 无效") from exc
    if length < 0:
        raise ValueError("Content-Length 无效")
    if length > MAX_REQUEST_BYTES:
        raise RequestTooLargeError(f"请求体不能超过 {MAX_REQUEST_BYTES // (1024 * 1024)} MB")
    raw = handler.rfile.read(length)
    if len(raw) != length:
        raise ValueError("请求体不完整")
    content_type = handler.headers.get("Content-Type", "")
    if content_type.startswith("multipart/form-data"):
        return parse_multipart(raw, content_type)
    return parse_json(raw)


def has_valid_image(fields: dict) -> bool:
    image = fields.get("_files", {}).get("image")
    content = image.get("content") if isinstance(image, dict) else None
    return isinstance(content, (bytes, bytearray)) and len(content) > 0


def validate_bind_security(host: str, token: str):
    if host.lower() == "localhost":
        return
    try:
        is_loopback = ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback and not token:
        raise ValueError("服务绑定到非本机地址时必须设置 API_TOKEN")


def has_valid_bearer_token(authorization: str, token: str) -> bool:
    if not token:
        return True
    scheme, separator, candidate = authorization.partition(" ")
    return (
        separator == " "
        and scheme.lower() == "bearer"
        and hmac.compare_digest(candidate.encode("utf-8"), token.encode("utf-8"))
    )


def allowed_cors_origin(origin: str, configured: str) -> str | None:
    """Return the exact allowed origin; never reflect arbitrary origins."""
    if not origin:
        return None
    allowed = {item.strip() for item in configured.split(",") if item.strip()}
    if not allowed:
        # Local file:// development sends Origin: null. Same-origin requests
        # do not need CORS headers at all.
        return "null" if origin == "null" else None
    return origin if origin in allowed else None


def valid_coordinate(value, minimum: float, maximum: float) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and minimum <= number <= maximum


def choose_species(mode: str, fields: dict):
    groups = MANGROVES if mode == "mangrove" else BIRDS
    image = fields.get("_files", {}).get("image", {})
    filename = image.get("filename", "")
    for keyword, species in groups.items():
        if keyword in filename:
            return species
    # 固定默认结果让前端无需准备特定图片也能联调。
    return next(iter(groups.values()))


class MockHandler(BaseHTTPRequestHandler):
    server_version = "MangroveMock/1.0"

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        cors_origin = allowed_cors_origin(
            self.headers.get("Origin", ""),
            os.environ.get("CORS_ORIGIN", ""),
        )
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        token = getattr(self.server, "api_token", os.environ.get("API_TOKEN", ""))
        return has_valid_bearer_token(self.headers.get("Authorization", ""), token)

    def reject_unauthorized(self):
        self.close_connection = True
        status, payload = error("需要有效的 Bearer API_TOKEN", 401)
        self.send_json(status, payload)

    def do_OPTIONS(self):
        self.send_response(204)
        cors_origin = allowed_cors_origin(
            self.headers.get("Origin", ""),
            os.environ.get("CORS_ORIGIN", ""),
        )
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if not self.authorized():
            self.reject_unauthorized()
            return
        path = urlparse(self.path).path
        if path == "/api/health":
            status, payload = response({"service": "mock", "status": "ok"})
            self.send_json(status, payload)
            return
        self.send_json(404, error("接口不存在", 404)[1])

    def do_POST(self):
        if not self.authorized():
            self.reject_unauthorized()
            return
        path = urlparse(self.path).path
        try:
            fields = parse_body(self)
            status, payload = self.route(path, fields)
        except RequestTooLargeError as exc:
            self.close_connection = True
            status, payload = error(str(exc), 413)
        except ValueError as exc:
            status, payload = error(str(exc))
        except Exception as exc:  # mock 服务要返回可读错误，便于前端联调
            status, payload = error(f"mock 服务异常：{exc}", 500)
        self.send_json(status, payload)

    def route(self, path: str, fields: dict):
        if path == "/api/recognition/species":
            mode = fields.get("mode")
            if mode not in ("mangrove", "bird"):
                return error("mode 必须是 mangrove 或 bird")
            if not has_valid_image(fields):
                return error("image 为必填项且文件内容不能为空")
            species = choose_species(mode, fields)
            return response({
                **species,
                "category": mode,
                "alternatives": [],
                "fallbackRequired": False,
            })

        if path == "/api/knowledge/ask":
            question = str(fields.get("question", "")).strip()
            if not question:
                return error("question 为必填项")
            return response(answer_question(question))

        if path == "/api/knowledge/explain":
            species_id = str(fields.get("speciesId", "")).strip()
            if not species_id:
                return error("speciesId 为必填项")
            return response({
                "title": "认识红树林物种",
                "script": "红树林是海岸线上的绿色卫士。观察它的根系、叶片和周围的小动物，你会发现一座充满生命的潮间带城市。",
                "durationSeconds": 45,
            })

        if path == "/api/audio/tts":
            text = str(fields.get("text", "")).strip()
            language = str(fields.get("language", "zh-CN"))
            if not text:
                return error("text 为必填项")
            if len(text) > MAX_TTS_TEXT_LENGTH:
                return error(f"text 不能超过 {MAX_TTS_TEXT_LENGTH} 个字符")
            if language not in ("zh-CN", "zh-HK", "en-US"):
                return error("language 必须是 zh-CN、zh-HK 或 en-US")
            return response({
                # Mock 不伪造可播放地址；前端收到 fallbackRequired 后使用浏览器 TTS。
                "audioUrl": None,
                "language": language,
                "durationSeconds": max(2, min(60, len(text) // 4)),
                "fallbackRequired": True,
                "provider": "browser",
            })

        if path == "/api/reports":
            report_type = fields.get("type")
            if report_type not in ("observation", "litter"):
                return error("type 必须是 observation 或 litter")
            if not valid_coordinate(fields.get("latitude"), -90, 90):
                return error("latitude 必须是 -90 到 90 之间的有限数字")
            if not valid_coordinate(fields.get("longitude"), -180, 180):
                return error("longitude 必须是 -180 到 180 之间的有限数字")
            species_id = fields.get("speciesId")
            if report_type == "observation" and (
                not isinstance(species_id, str) or not species_id.strip()
            ):
                return error("observation 必须提供 speciesId")
            if report_type == "observation" and species_id not in VALID_REPORT_SPECIES:
                return error("speciesId 不在当前识别目录中")
            return response({"reportId": f"report_{uuid.uuid4().hex[:8]}", "status": "received"})

        return error("接口不存在", 404)


def main():
    host = os.environ.get("HOST", HOST)
    port = int(os.environ.get("PORT", str(PORT)))
    token = os.environ.get("API_TOKEN", "")
    validate_bind_security(host, token)
    server = ThreadingHTTPServer((host, port), MockHandler)
    server.api_token = token
    print(f"Mock 服务已启动：http://{host}:{port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMock 服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
