r"""One-command local demo restore with strict model hash verification.

Usage:
    python tools/setup_local_demo.py --model D:\models\model.onnx
    python tools/setup_local_demo.py --model https://example.invalid/model.onnx

The model binary is intentionally not in Git. This script installs the runtime
dependencies, verifies the model against models/recognition/manifest.json,
writes the local deployment metrics, starts the API and demo server, and exits 0
only after /api/health reports a ready model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "models" / "recognition" / "manifest.json"
REPORT = ROOT / "data" / "recognition-balance-20261021" / "expanded-resnet18-metrics.json"
ARTIFACTS = ROOT / "backend" / "recognition" / "artifacts"
LOG_DIR = ROOT / ".local-demo"
VALIDATION_SPLIT = "new-batch-photographer-holdout-no-historical-author-overlap"
EXPECTED_MODEL_VERSION = "resnet18-expanded-onnx-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: cannot read {path}: {exc}")
    if not isinstance(value, dict):
        raise SystemExit(f"ERROR: {path} must be a JSON object")
    return value


def fail(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def resolve_model(model_arg: str | None, manifest: dict) -> Path:
    if model_arg:
        if model_arg.startswith(("http://", "https://")):
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            target = LOG_DIR / "download.model.onnx"
            print(f"Downloading model from {model_arg} ...", flush=True)
            try:
                urllib.request.urlretrieve(model_arg, target)
            except Exception as exc:  # noqa: BLE001 - report any download failure
                fail(f"model download failed: {exc}")
            return target
        path = Path(model_arg).expanduser().resolve()
        if not path.is_file():
            fail(f"model file does not exist: {path}")
        return path

    existing = ARTIFACTS / "model.onnx"
    if existing.is_file() and sha256_file(existing) == manifest["sha256"]:
        print(f"Using existing verified model: {existing}", flush=True)
        return existing
    url = manifest.get("downloadUrl")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        target = LOG_DIR / "download.model.onnx"
        print(f"Downloading model from manifest URL ...", flush=True)
        try:
            urllib.request.urlretrieve(url, target)
        except Exception as exc:  # noqa: BLE001
            fail(f"model download failed: {exc}")
        return target
    fail(
        "no model supplied and manifest downloadUrl is null.\n"
        f"Pass --model PATH_OR_URL. Expected SHA-256: {manifest['sha256']} "
        f"({manifest['bytes']} bytes).",
        2,
    )


def verify_manifest_and_report(manifest_path: Path, report_path: Path, model_path: Path) -> tuple[dict, dict]:
    manifest = load_json(manifest_path)
    report = load_json(report_path)
    needed = ["modelVersion", "sha256", "bytes", "classes"]
    if any(key not in manifest for key in needed):
        fail(f"manifest is missing one of {needed}")
    if manifest["modelVersion"] != EXPECTED_MODEL_VERSION:
        fail(f"unsupported modelVersion: {manifest['modelVersion']}")
    expected_sha = str(manifest["sha256"]).lower()
    if len(expected_sha) != 64:
        fail("manifest sha256 must be 64 hex characters")
    actual_size = model_path.stat().st_size
    if actual_size != manifest["bytes"]:
        fail(f"model size mismatch: expected {manifest['bytes']}, got {actual_size}")
    actual_sha = sha256_file(model_path)
    if actual_sha != expected_sha:
        fail(f"model SHA-256 mismatch: expected {expected_sha}, got {actual_sha}")
    if report.get("modelSha256", "").lower() != expected_sha:
        fail("experiment report modelSha256 does not match manifest")
    if report.get("modelBytes") != manifest["bytes"]:
        fail("experiment report modelBytes does not match manifest")
    if report.get("readyForDemo") is not False:
        fail("experiment report must keep readyForDemo: false")
    accuracy = report.get("developmentAccuracy")
    if isinstance(accuracy, bool) or not isinstance(accuracy, (int, float)) or accuracy < 0.75:
        fail("developmentAccuracy is below the 0.75 local-demo gate")
    if report.get("developmentSamples", 0) < 20:
        fail("developmentSamples is below 20")
    if report.get("classes") != manifest["classes"]:
        fail("manifest classes do not match experiment report")
    try:
        catalog = json.loads((ROOT / "data" / "species.catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read species catalog: {exc}")
    if not isinstance(catalog, list):
        fail("species catalog must be an array")
    expected_classes = {item["speciesId"] for item in catalog if item.get("category") == "mangrove"}
    if set(manifest["classes"]) != expected_classes:
        fail("manifest classes do not match species.catalog.json")
    return manifest, report


def ensure_venv(venv_arg: str, skip_install: bool) -> Path:
    venv_dir = Path(venv_arg)
    if not venv_dir.is_absolute():
        venv_dir = (ROOT / venv_dir).resolve()
    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        print(f"Creating virtual environment: {venv_dir}", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], cwd=ROOT, check=True)
    if not python.is_file():
        fail(f"virtual environment python not found: {python}")
    if not skip_install:
        print("Installing runtime dependencies ...", flush=True)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", "backend/recognition/requirements.txt"],
            cwd=ROOT,
            check=True,
        )
    return python


def write_metrics(manifest: dict, report: dict) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    metrics = dict(report)
    metrics.update({
        "model": manifest["modelVersion"],
        "validationAccuracy": report["developmentAccuracy"],
        "validationSplit": VALIDATION_SPLIT,
        "readyForDemo": True,
        "demoActivation": "one-command-local-demo",
        "deploymentNote": (
            "Installed by tools/setup_local_demo.py after SHA-256 verification. "
            "This is local-demo-only; the 29-image online-photo development set is not "
            "Zhanjiang field validation."
        ),
        "modelSha256": manifest["sha256"],
    })
    temporary = ARTIFACTS / "metrics.setup.tmp"
    temporary.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(ARTIFACTS / "metrics.json")


def install_model(model_path: Path, model_sha: str) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    target = ARTIFACTS / "model.onnx"
    temporary = ARTIFACTS / "model.setup.tmp.onnx"
    temporary.write_bytes(model_path.read_bytes())
    if sha256_file(temporary) != model_sha:
        temporary.unlink(missing_ok=True)
        fail("copied model failed SHA-256 verification")
    temporary.replace(target)
    return target


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_process(command: list[str], log_path: Path, env: dict[str, str]) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8")
    kwargs = {"cwd": ROOT, "env": env, "stdout": log, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    process._log_handle = log  # keep the handle alive for the parent
    return process


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def read_tail(path: Path, lines: int = 30) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


def wait_health(port: int, timeout: float, api: subprocess.Popen, demo: subprocess.Popen, api_log: Path, demo_log: Path) -> dict:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    last_error = "health check did not run"
    while time.time() < deadline:
        if api.poll() is not None:
            last_error = f"API exited with {api.returncode}\n{read_tail(api_log)}"
            break
        if demo.poll() is not None:
            last_error = f"demo server exited with {demo.returncode}\n{read_tail(demo_log)}"
            break
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            data = payload.get("data", {})
            if data.get("mangroveModelReady") is True:
                scope = data.get("mangroveValidationScope")
                field_validated = data.get("mangroveFieldValidated")
                if scope is not None and scope != "local-demo-only":
                    last_error = f"unexpected mangroveValidationScope: {scope}"
                elif field_validated is not None and field_validated is not False:
                    last_error = f"unexpected mangroveFieldValidated: {field_validated}"
                else:
                    return data
            else:
                last_error = f"model not ready yet: {data}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(last_error)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="local path or HTTPS URL of model.onnx")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--venv", default=".venv")
    parser.add_argument("--skip-install", action="store_true", help="reuse an existing venv without pip install")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--demo-port", type=int, default=5173)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    if not MANIFEST.is_file():
        fail(f"manifest not found: {MANIFEST}")
    if not REPORT.is_file():
        fail(f"experiment report not found: {REPORT}")
    model_source = resolve_model(args.model, load_json(args.manifest))
    manifest, report = verify_manifest_and_report(args.manifest, args.report, model_source)
    python = ensure_venv(args.venv, args.skip_install)
    manifest, report = verify_manifest_and_report(args.manifest, args.report, model_source)
    installed = install_model(model_source, manifest["sha256"])
    write_metrics(manifest, report)

    if port_in_use(args.api_port):
        fail(f"port {args.api_port} is already in use; stop the old API first")
    if port_in_use(args.demo_port):
        fail(f"port {args.demo_port} is already in use; stop the old demo server first")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    api_log = LOG_DIR / "api.log"
    demo_log = LOG_DIR / "demo.log"
    env = os.environ.copy()
    env.update({"REQUIRE_MODEL": "1", "PYTHONIOENCODING": "utf-8", "HOST": "127.0.0.1", "PORT": str(args.api_port)})
    api = start_process([str(python), "backend/recognition/api.py"], api_log, env)
    demo = start_process([str(python), "tools/serve_local_demo.py", "--port", str(args.demo_port)], demo_log, env)
    try:
        health = wait_health(args.demo_port, args.timeout, api, demo, api_log, demo_log)
    except RuntimeError as exc:
        stop_process(api)
        stop_process(demo)
        fail(f"health check failed: {exc}", 1)

    pids = {
        "apiPid": api.pid,
        "demoPid": demo.pid,
        "apiPort": args.api_port,
        "demoPort": args.demo_port,
        "url": f"http://127.0.0.1:{args.demo_port}/",
        "modelVersion": manifest["modelVersion"],
        "modelSha256": manifest["sha256"],
        "health": health,
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }
    (LOG_DIR / "pids.json").write_text(json.dumps(pids, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(pids, ensure_ascii=False, indent=2))
    print("Local demo is ready.", flush=True)


if __name__ == "__main__":
    main()
