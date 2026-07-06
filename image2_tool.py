import base64
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    NORMAL,
    Canvas,
    PhotoImage,
    StringVar,
    Text,
    Tk,
    filedialog,
    messagebox,
    ttk,
)

import requests


APP_TITLE = "Ai炫滔 Image2 生图工具"
BASE_URL = "https://chunxueapi.com/v1"
FALLBACK_BASE_URLS = ("https://www.chunxueapi.com/v1",)
MODEL = "gpt-image-2"
SIZES = ("auto", "1024x1024", "1536x1024", "1024x1536", "2048x2048", "4096x4096")
EDIT_RETRY_ATTEMPTS = 12
EDIT_RETRY_DELAY_SECONDS = 18
QUOTA_ERROR_MESSAGE = "余额不足，请充值后再试"
UPSTREAM_ERROR_MESSAGE = "请求失败，服务暂时不可用，请稍后重试"
NETWORK_ERROR_PREFIX = "网络连接失败，请检查网络或代理后重试"
WEB_REFERER = "https://image.chunxueapi.com/"
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)
LOCAL_SAFETY_MESSAGE = "status code=400,非常抱歉，该提示可能违反了关于裸露、色情或情色内容的防护限制。如果你认为此判断有误，请重试或修改提示语。"
LOCAL_SAFETY_CHINESE_TERMS = (
    "裸露",
    "裸漏",
    "裸体",
    "全裸",
    "半裸",
    "露点",
    "色情",
    "情色",
    "性爱",
    "性交",
    "做爱",
    "性行为",
    "性器官",
    "生殖器",
    "阴部",
    "阴茎",
    "阴道",
    "乳头",
    "乳晕",
    "裸照",
    "成人内容",
)
LOCAL_SAFETY_ENGLISH_TERMS = (
    "nude",
    "nudity",
    "naked",
    "porn",
    "pornographic",
    "erotic",
    "erotica",
    "sexual",
    "sex",
    "nsfw",
    "topless",
    "nipples",
    "genitals",
    "vagina",
    "penis",
    "pussy",
    "cock",
    "blowjob",
    "hentai",
)
THEME_LABELS = {
    "deep": "深海黑",
    "light": "月光白",
    "mist": "雾蓝灰",
    "forest": "森林绿",
}
THEME_OPTIONS = tuple(THEME_LABELS.values())


def theme_palette(name: str) -> dict[str, str]:
    lookup = {label: key for key, label in THEME_LABELS.items()}
    key = lookup.get(name, name)
    palettes = {
        "light": {
            "black": "#e9edf5",
            "ink": "#dce3ef",
            "panel": "#f5f7fb",
            "paper": "#ffffff",
            "field": "#f2f5fa",
            "line": "#c9d3e3",
            "muted": "#5e6f8d",
            "accent": "#2563eb",
            "ice": "#142033",
            "scene_a": "#edf4ff",
            "scene_b": "#cfe4ff",
            "mountain": "#b9c9dd",
            "water": "#6ca7e8",
            "button": "#e3ebf7",
            "primary": "#142033",
            "primary_fg": "#ffffff",
        },
        "mist": {
            "black": "#111827",
            "ink": "#182235",
            "panel": "#202b3d",
            "paper": "#263448",
            "field": "#1a2536",
            "line": "#3d4e67",
            "muted": "#b6c2d6",
            "accent": "#93c5fd",
            "ice": "#f3f7ff",
            "scene_a": "#172033",
            "scene_b": "#344860",
            "mountain": "#121926",
            "water": "#5ba7e8",
            "button": "#31445d",
            "primary": "#dbeafe",
            "primary_fg": "#111827",
        },
        "forest": {
            "black": "#07130f",
            "ink": "#0d1f19",
            "panel": "#102820",
            "paper": "#17362c",
            "field": "#0c211b",
            "line": "#2c5a4b",
            "muted": "#a7c7ba",
            "accent": "#86efac",
            "ice": "#ecfff4",
            "scene_a": "#07130f",
            "scene_b": "#184b3b",
            "mountain": "#06100d",
            "water": "#34d399",
            "button": "#1f4d3f",
            "primary": "#d1fae5",
            "primary_fg": "#07130f",
        },
        "deep": {
            "black": "#030817",
            "ink": "#071126",
            "panel": "#06142d",
            "paper": "#0a1b3a",
            "field": "#07162f",
            "line": "#2c4675",
            "muted": "#92a9d6",
            "accent": "#67e8f9",
            "ice": "#dbe7ff",
            "scene_a": "#06142d",
            "scene_b": "#0b2a64",
            "mountain": "#030817",
            "water": "#1fb7ff",
            "button": "#101f3d",
            "primary": "#dbe7ff",
            "primary_fg": "#06142d",
        },
    }
    return palettes.get(key, palettes["deep"])


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def asset_path(*parts: str) -> Path:
    return app_root().joinpath(*parts)


def writable_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def log_path() -> Path:
    return writable_app_dir() / "image2_generation_log.jsonl"


def diagnostic_log_path() -> Path:
    return writable_app_dir() / "image2_diagnostic_log.jsonl"


_INSTANCE_LOCK_FILE = None


@dataclass
class GenerationResult:
    image_path: Path


class Image2Error(Exception):
    pass


def endpoints_for(suffix: str) -> list[str]:
    endpoints: list[str] = []
    for base_url in (BASE_URL, *FALLBACK_BASE_URLS):
        endpoint = f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"
        if endpoint not in endpoints:
            endpoints.append(endpoint)
    return endpoints


def should_retry_endpoint(error: Image2Error) -> bool:
    message = str(error)
    lowered = message.lower()
    retry_markers = (
        "curl 未返回 http 状态码",
        "curl 调用失败",
        "http 502",
        "http 503",
        "http 524",
        "bad gateway",
        "service unavailable",
        "no available compatible accounts",
    )
    if "暂时不可用" in message or "稍后重试" in message:
        return True
    if any(marker in lowered for marker in retry_markers):
        return True
    return message in {
        UPSTREAM_ERROR_MESSAGE,
        "curl 未返回 HTTP 状态码。",
    } or message.startswith("curl 调用失败：")


def guess_upload_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def ensure_png_name(name: str) -> str:
    cleaned = name.strip().strip('"').strip("'")
    if not cleaned:
        cleaned = f"image2_{timestamp()}.png"
    if not cleaned.lower().endswith(".png"):
        cleaned += ".png"
    return cleaned


def violates_local_safety(prompt: str) -> bool:
    normalized = prompt.strip().lower()
    if not normalized:
        return False
    if any(term in normalized for term in LOCAL_SAFETY_CHINESE_TERMS):
        return True

    padded = "".join(ch if ch.isalnum() else " " for ch in normalized)
    words = set(padded.split())
    return any(term in words for term in LOCAL_SAFETY_ENGLISH_TERMS)


def load_env_key() -> str:
    key = os.environ.get("CHUNXUE_API_KEY", "").strip()
    if key or not sys.platform.startswith("win"):
        return key
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env_key:
            value, _ = winreg.QueryValueEx(env_key, "CHUNXUE_API_KEY")
        return str(value).strip()
    except OSError:
        return ""


def key_fingerprint(api_key: str) -> str:
    key = api_key.strip()
    if not key:
        return "empty"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
    return f"len={len(key)} sha256={digest} head={key[:5]} tail={key[-4:]}"


def browser_like_headers() -> list[str]:
    return [
        f"Referer: {WEB_REFERER}",
        "Accept-Language: zh-CN",
        f"User-Agent: {WEB_USER_AGENT}",
        'sec-ch-ua-platform: "Windows"',
        'sec-ch-ua: "Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile: ?0",
    ]


def save_user_env_key(api_key: str) -> None:
    if not sys.platform.startswith("win"):
        raise Image2Error("保存环境变量仅支持 Windows。")
    if not api_key.strip():
        raise Image2Error("访问密钥为空，不能保存。")

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "CHUNXUE_API_KEY", 0, winreg.REG_SZ, api_key.strip())
        os.environ["CHUNXUE_API_KEY"] = api_key.strip()
    except OSError as error:
        raise Image2Error(f"保存用户环境变量失败：{error}") from error


def clear_user_env_key() -> None:
    if not sys.platform.startswith("win"):
        raise Image2Error("删除环境变量仅支持 Windows。")
    try:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                try:
                    winreg.DeleteValue(key, "CHUNXUE_API_KEY")
                except FileNotFoundError:
                    pass
        except OSError as error:
            raise Image2Error(f"删除用户环境变量失败：{error}") from error

        os.environ.pop("CHUNXUE_API_KEY", None)
    except OSError as error:
        raise Image2Error(f"删除用户环境变量失败：{error}") from error


def find_curl() -> str:
    curl_path = shutil.which("curl.exe") or shutil.which("curl")
    if not curl_path:
        raise Image2Error("未找到 curl.exe。Windows 10/11 通常自带 curl，请确认它在 PATH 中。")
    return curl_path


def acquire_single_instance_lock() -> bool:
    global _INSTANCE_LOCK_FILE
    if not sys.platform.startswith("win"):
        return True
    try:
        import msvcrt

        lock_file = (writable_app_dir() / "Image2Tool.lock").open("a+b")
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        _INSTANCE_LOCK_FILE = lock_file
        return True
    except OSError:
        return False


def write_json_utf8_no_bom(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def raw_error_message(response_text: str) -> str:
    if not response_text:
        return ""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text[:500]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if error:
        return str(error)
    if isinstance(data, dict) and data.get("message"):
        return str(data["message"])
    return ""


def append_diagnostic(record: dict) -> None:
    try:
        path = diagnostic_log_path()
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def summarize_curl_args(args: list[str]) -> dict:
    summary: dict[str, object] = {
        "endpoint": "",
        "upload_field": "",
        "form": {},
        "api_key": "unknown",
        "headers": {},
    }
    forms: dict[str, str] = {}
    headers: dict[str, str] = {}
    for index, arg in enumerate(args):
        if isinstance(arg, str) and arg.startswith(("http://", "https://")) and not summary["endpoint"]:
            summary["endpoint"] = arg
        if arg == "-H" and index + 1 < len(args):
            header = args[index + 1]
            if header.lower().startswith("authorization: bearer "):
                summary["api_key"] = key_fingerprint(header.split(" ", 2)[-1])
            elif ":" in header:
                name, value = header.split(":", 1)
                name = name.strip()
                if name.lower() not in {"authorization", "cookie"}:
                    headers[name] = value.strip()
        if arg == "--form-string" and index + 1 < len(args):
            item = args[index + 1]
            if "=" in item:
                name, value = item.split("=", 1)
                if name != "prompt":
                    forms[name] = value
        if arg == "-F" and index + 1 < len(args):
            upload = args[index + 1]
            if "=@" in upload:
                summary["upload_field"] = upload.split("=@", 1)[0]
    summary["form"] = forms
    summary["headers"] = headers
    return summary


def parse_service_response(response_text: str) -> dict:
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    stream_items: list[dict] = []
    for line in response_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line.split(":", 1)[1].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            item = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            stream_items.append(item)

    image_items = [
        item
        for item in stream_items
        if item.get("b64_json") or item.get("url") or item.get("revised_prompt")
    ]
    if image_items:
        return {"data": image_items, "stream_events": stream_items}

    raise Image2Error("服务响应不是合法记录，也没有可保存的流式图片数据。")


def run_curl(args: list[str], response_path: Path, timeout_seconds: int = 420) -> dict:
    curl_path = find_curl()
    command = [curl_path, "-sS", "-w", "\nHTTP_STATUS:%{http_code}\n", *args, "-o", str(response_path)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
    )

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    status = ""
    for line in stdout.splitlines():
        if line.startswith("HTTP_STATUS:"):
            status = line.split(":", 1)[1].strip()

    response_text = ""
    if response_path.exists():
        response_text = response_path.read_text(encoding="utf-8", errors="replace")

    if result.returncode != 0:
        append_diagnostic(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "curl_failed",
                **summarize_curl_args(args),
                "stderr": stderr.strip(),
                "stdout": stdout.strip(),
            }
        )
        raise Image2Error(f"{NETWORK_ERROR_PREFIX}: {stderr.strip() or stdout.strip() or result.returncode}")
    if not status:
        append_diagnostic(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "missing_http_status",
                **summarize_curl_args(args),
                "stderr": stderr.strip(),
                "stdout": stdout.strip(),
            }
        )
        raise Image2Error("curl 未返回 HTTP 状态码。")
    if not status.isdigit() or int(status) < 200 or int(status) >= 300:
        raw_detail = raw_error_message(response_text) or response_text[:500] or stderr.strip()
        detail = extract_error_message(response_text) or normalize_service_error(
            f"HTTP {status} {response_text[:1000] or stderr.strip()}"
        )
        append_diagnostic(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "http_error",
                **summarize_curl_args(args),
                "http_status": status,
                "raw_message": raw_detail,
                "normalized_message": detail,
            }
        )
        if detail in {QUOTA_ERROR_MESSAGE, UPSTREAM_ERROR_MESSAGE}:
            raise Image2Error(detail)
        raise Image2Error(f"服务返回 HTTP {status}：{detail}")

    try:
        data = parse_service_response(response_text)
    except Image2Error as error:
        append_diagnostic(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "parse_error",
                **summarize_curl_args(args),
                "http_status": status,
                "message": str(error),
                "response_head": response_text[:500],
            }
        )
        raise
    append_diagnostic(
        {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "success",
            **summarize_curl_args(args),
            "http_status": status,
        }
    )
    return data


def run_edit_requests(
    endpoint: str,
    api_key: str,
    prompt: str,
    image_file: Path,
    image_field: str,
    image_type: str,
    response_path: Path,
    timeout_seconds: int = 660,
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Referer": WEB_REFERER,
        "Accept-Language": "zh-CN",
        "User-Agent": WEB_USER_AGENT,
    }
    data = [
        ("model", MODEL),
        ("prompt", prompt.strip()),
        ("size", "auto"),
        ("output_format", "png"),
        ("background", "auto"),
        ("moderation", "auto"),
        ("quality", "auto"),
    ]
    summary = {
        "endpoint": endpoint,
        "upload_field": image_field,
        "form": {
            "model": MODEL,
            "size": "auto",
            "output_format": "png",
            "background": "auto",
            "moderation": "auto",
            "quality": "auto",
        },
        "api_key": key_fingerprint(api_key),
        "headers": {
            "Referer": WEB_REFERER,
            "Accept-Language": "zh-CN",
            "User-Agent": WEB_USER_AGENT,
        },
        "transport": "requests",
        "filename": "input-1.png",
    }
    try:
        with image_file.open("rb") as file:
            response = requests.post(
                endpoint,
                headers=headers,
                data=data,
                files=[(image_field, ("input-1.png", file, image_type))],
                timeout=timeout_seconds,
            )
    except requests.RequestException as error:
        append_diagnostic(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "requests_failed",
                **summary,
                "error": str(error),
            }
        )
        raise Image2Error(f"{NETWORK_ERROR_PREFIX}: {error}") from error

    response_text = response.text or ""
    response_path.write_text(response_text, encoding="utf-8", errors="replace")
    if response.status_code < 200 or response.status_code >= 300:
        raw_detail = raw_error_message(response_text) or response_text[:500]
        detail = extract_error_message(response_text) or normalize_service_error(
            f"HTTP {response.status_code} {response_text[:1000]}"
        )
        append_diagnostic(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "http_error",
                **summary,
                "http_status": str(response.status_code),
                "raw_message": raw_detail,
                "normalized_message": detail,
            }
        )
        if detail in {QUOTA_ERROR_MESSAGE, UPSTREAM_ERROR_MESSAGE}:
            raise Image2Error(detail)
        raise Image2Error(f"服务返回 HTTP {response.status_code}：{detail}")

    try:
        data = parse_service_response(response_text)
    except Image2Error as error:
        append_diagnostic(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "parse_error",
                **summary,
                "http_status": str(response.status_code),
                "message": str(error),
                "response_head": response_text[:500],
            }
        )
        raise

    append_diagnostic(
        {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "success",
            **summary,
            "http_status": str(response.status_code),
        }
    )
    return data


def extract_error_message(response_text: str) -> str:
    if not response_text:
        return ""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return normalize_service_error(response_text[:1000])
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        raw_message = str(error.get("message") or error)
        return normalize_service_error(raw_message)
    if error:
        return normalize_service_error(str(error))
    if isinstance(data, dict) and data.get("message"):
        return normalize_service_error(str(data["message"]))
    return ""


def normalize_service_error(message: str) -> str:
    lowered = message.lower()
    quota_markers = (
        "pre_consume_token_quota_failed",
        "token quota is not enough",
        "quota is not enough",
        "remain quota",
        "need quota",
    )
    if any(marker in lowered for marker in quota_markers):
        return QUOTA_ERROR_MESSAGE
    upstream_markers = (
        "upstream service temporarily unavailable",
        "error code: 502",
        "error code: 503",
        "error code: 524",
        "bad gateway",
        "service unavailable",
        "no available compatible accounts",
        "http 502",
        "http 503",
        "http 524",
    )
    if any(marker in lowered for marker in upstream_markers):
        return UPSTREAM_ERROR_MESSAGE
    return message


def save_image_from_response(data: dict, image_path: Path) -> None:
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise Image2Error("服务响应缺少图片数据。")

    first = items[0]
    b64_data = first.get("b64_json")
    url = first.get("url")

    if b64_data:
        image_path.write_bytes(base64.b64decode(b64_data))
        return

    if isinstance(url, str) and url.startswith("data:image"):
        comma = url.find(",")
        if comma < 0:
            raise Image2Error("data:image 响应格式不完整。")
        image_path.write_bytes(base64.b64decode(url[comma + 1 :]))
        return

    if isinstance(url, str) and url.startswith(("http://", "https://")):
        with urllib.request.urlopen(url, timeout=360) as response:
            image_path.write_bytes(response.read())
        return

    raise Image2Error("服务响应不包含可保存的图片数据。")


def validate_common(api_key: str, prompt: str, output_dir: Path, filename: str) -> Path:
    if not api_key.strip():
        raise Image2Error("请填写访问密钥，或先保存本机密钥。")
    if not prompt.strip():
        raise Image2Error("请填写提示词。")
    if violates_local_safety(prompt):
        raise Image2Error(LOCAL_SAFETY_MESSAGE)
    if not output_dir.exists() or not output_dir.is_dir():
        raise Image2Error("输出目录不存在或不是文件夹。")

    image_path = output_dir / ensure_png_name(filename)
    if image_path.exists():
        stem = image_path.stem
        image_path = image_path.with_name(f"{stem}_{timestamp()}.png")
    return image_path


def generate_image(api_key: str, prompt: str, size: str, output_dir: Path, filename: str) -> GenerationResult:
    image_path = validate_common(api_key, prompt, output_dir, filename)

    with tempfile.TemporaryDirectory(prefix="image2_tool_") as temp_dir:
        body_path = Path(temp_dir) / "request.json"
        raw_response_path = Path(temp_dir) / "response.json"
        write_json_utf8_no_bom(
            body_path,
            {
                "model": MODEL,
                "prompt": prompt.strip(),
                "n": 1,
                "quality": "auto",
                "size": size,
                "output_format": "png",
            },
        )
        last_error: Image2Error | None = None
        for endpoint in endpoints_for("images/generations"):
            try:
                data = run_curl(
                    [
                        "-X",
                        "POST",
                        endpoint,
                        "-H",
                        f"Authorization: Bearer {api_key.strip()}",
                        "-H",
                        "Content-Type: application/json",
                        "--data-binary",
                        f"@{body_path}",
                    ],
                    raw_response_path,
                )
                break
            except Image2Error as error:
                if not should_retry_endpoint(error):
                    raise
                last_error = error
        else:
            raise last_error or Image2Error(UPSTREAM_ERROR_MESSAGE)

    save_image_from_response(data, image_path)
    return GenerationResult(image_path=image_path)


def edit_image(
    api_key: str,
    prompt: str,
    size: str,
    output_dir: Path,
    filename: str,
    image_file: Path,
    mask_file: Path | None,
) -> GenerationResult:
    image_path = validate_common(api_key, prompt, output_dir, filename)
    if not image_file.exists() or not image_file.is_file():
        raise Image2Error("改图模式需要选择有效的原图文件。")
    if mask_file and (not mask_file.exists() or not mask_file.is_file()):
        raise Image2Error("Mask 文件不存在或不是文件。")

    # The ChunXue web UI sends image-to-image requests with size=auto.
    # Fixed sizes currently route to a less stable upstream and often return 502.
    edit_size = "auto"
    with tempfile.TemporaryDirectory(prefix="image2_tool_") as temp_dir:
        raw_response_path = Path(temp_dir) / "response.json"
        last_error: Image2Error | None = None
        upload_type = guess_upload_type(image_file)
        mask_type = guess_upload_type(mask_file) if mask_file else ""
        edit_routes = [
            (endpoints_for("images/edits")[0], "image", EDIT_RETRY_ATTEMPTS),
            (endpoints_for("images/edits")[0], "image[]", 3),
        ]
        fallback_endpoints = endpoints_for("images/edits")[1:]
        edit_routes.extend((endpoint, "image", 3) for endpoint in fallback_endpoints)
        edit_routes.extend((endpoint, "image[]", 3) for endpoint in fallback_endpoints)

        for endpoint, image_field, max_attempts in edit_routes:
            for attempt in range(1, max_attempts + 1):
                args = [
                    "-X",
                    "POST",
                    endpoint,
                    "-H",
                    f"Authorization: Bearer {api_key.strip()}",
                    *sum((["-H", header] for header in browser_like_headers()), []),
                    "--form-string",
                    f"model={MODEL}",
                    "--form-string",
                    f"prompt={prompt.strip()}",
                    "--form-string",
                    f"size={edit_size}",
                    "--form-string",
                    "output_format=png",
                    "--form-string",
                    "background=auto",
                    "--form-string",
                    "moderation=auto",
                    "--form-string",
                    "quality=auto",
                    "-F",
                    f"{image_field}=@{image_file};filename=input-1.png;type={upload_type}",
                ]
                if mask_file:
                    args.extend(["-F", f"mask=@{mask_file};type={mask_type}"])
                try:
                    if mask_file:
                        data = run_curl(args, raw_response_path)
                    else:
                        data = run_edit_requests(
                            endpoint=endpoint,
                            api_key=api_key,
                            prompt=prompt,
                            image_file=image_file,
                            image_field=image_field,
                            image_type=upload_type,
                            response_path=raw_response_path,
                        )
                    break
                except Image2Error as error:
                    if not should_retry_endpoint(error):
                        raise
                    last_error = error
                    append_diagnostic(
                        {
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "event": "retry_after_error",
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "message": str(error),
                            **summarize_curl_args(args),
                        }
                    )
                    if attempt < max_attempts:
                        time.sleep(EDIT_RETRY_DELAY_SECONDS)
            else:
                continue
            break
        else:
            raise last_error or Image2Error(UPSTREAM_ERROR_MESSAGE)

    save_image_from_response(data, image_path)
    return GenerationResult(image_path=image_path)


class Image2App:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1220x820")
        self.root.minsize(1020, 680)
        self.root.configure(bg="#030817")

        self.mode = StringVar(value="generate")
        self.api_key = StringVar(value=load_env_key())
        self.size = StringVar(value="auto")
        self.output_dir = StringVar(value=str(Path.cwd()))
        self.filename = StringVar(value=f"image2_{timestamp()}.png")
        self.image_file = StringVar(value="")
        self.mask_file = StringVar(value="")
        self.status = StringVar(value="准备就绪")
        self.theme_name = StringVar(value="月光白")
        self.colors = theme_palette(self.theme_name.get())
        self.success_count = StringVar(value="成功 0 张")
        self.failure_count = StringVar(value="失败 0 张")
        self.log_summary = StringVar(value="暂无生成日志")
        self.last_image_path: Path | None = None
        self.logo_image: PhotoImage | None = None
        self.scene_canvas: Canvas | None = None
        self.scroll_canvas: Canvas | None = None
        self.prompt_text: Text | None = None
        self.log_text: Text | None = None

        self._set_icon()
        self._build_ui()
        self._refresh_log_view()
        self._toggle_edit_fields()

    def _set_icon(self) -> None:
        ico_path = asset_path("assets", "xuantao.ico")
        png_path = asset_path("assets", "xuantao_icon.png")
        try:
            if ico_path.exists():
                self.root.iconbitmap(default=str(ico_path))
            if png_path.exists():
                self.logo_image = PhotoImage(file=str(png_path))
                self.root.iconphoto(True, self.logo_image)
        except Exception:
            pass

    def _build_ui(self) -> None:
        self._apply_theme()

        main = ttk.Frame(self.root, style="App.TFrame", padding=20)
        main.pack(fill=BOTH, expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(main, style="Sidebar.TFrame", padding=(18, 20, 16, 18))
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 18))
        sidebar.configure(width=236)
        sidebar.grid_propagate(False)
        self._build_sidebar(sidebar)

        workspace = ttk.Frame(main, style="Panel.TFrame")
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.rowconfigure(1, weight=1)
        workspace.columnconfigure(0, weight=1)

        header = ttk.Frame(workspace, style="Panel.TFrame", padding=(22, 18, 22, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="创作工作台", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="沉浸式生图控制台", style="Heading.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))

        theme_bar = ttk.Frame(header, style="Panel.TFrame")
        theme_bar.grid(row=0, column=1, rowspan=2, sticky="e", padx=(14, 0))
        ttk.Label(theme_bar, text="背景", style="FieldPanel.TLabel").pack(side="left", padx=(0, 8))
        theme_combo = ttk.Combobox(theme_bar, textvariable=self.theme_name, values=THEME_OPTIONS, state="readonly", width=8)
        theme_combo.pack(side="left")
        theme_combo.bind("<<ComboboxSelected>>", lambda _event: self._change_theme())
        ttk.Button(theme_bar, text="重置文件名", style="Ghost.TButton", command=self._reset_filename).pack(side="left", padx=(10, 0))

        scroll_host = ttk.Frame(workspace, style="Panel.TFrame")
        scroll_host.grid(row=1, column=0, sticky="nsew")
        scroll_host.rowconfigure(0, weight=1)
        scroll_host.columnconfigure(0, weight=1)

        canvas = Canvas(scroll_host, bg="#06142d", highlightthickness=0)
        self.scroll_canvas = canvas
        scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview)
        form = ttk.Frame(canvas, style="Panel.TFrame", padding=(22, 0, 22, 16))
        canvas_window = canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        def update_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_form_width(event) -> None:
            canvas.itemconfigure(canvas_window, width=max(event.width - 2, 760))

        def on_mousewheel(event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        form.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_form_width)
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        self._build_scene(form)
        self._build_form(form)
        self._build_footer(workspace)

    def _change_theme(self) -> None:
        self._apply_theme()
        self.root.update_idletasks()

    def _build_scene(self, parent: ttk.Frame) -> None:
        scene = ttk.Frame(parent, style="Scene.TFrame", padding=(0, 0, 0, 16))
        scene.pack(fill="x")
        scene.columnconfigure(0, weight=1)

        canvas = Canvas(scene, height=190, bg="#06142d", highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="ew")
        self.scene_canvas = canvas
        canvas.bind("<Configure>", self._draw_scene)

        meta = ttk.Frame(scene, style="Panel.TFrame", padding=(4, 10, 4, 0))
        meta.grid(row=1, column=0, sticky="ew")
        meta.columnconfigure(0, weight=1)
        ttk.Label(meta, text="视觉生成引擎", style="SceneMeta.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(meta, text="提示词、原图、输出路径集中管理。", style="SceneTitle.TLabel", wraplength=620).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(4, 0),
        )

    def _draw_scene(self, event=None) -> None:
        canvas = self.scene_canvas
        if canvas is None:
            return
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        colors = self.colors
        canvas.delete("all")

        for i in range(0, height, 3):
            ratio = i / max(height, 1)
            start = colors["scene_a"].lstrip("#")
            end = colors["scene_b"].lstrip("#")
            sr, sg, sb = int(start[0:2], 16), int(start[2:4], 16), int(start[4:6], 16)
            er, eg, eb = int(end[0:2], 16), int(end[2:4], 16), int(end[4:6], 16)
            r = int(sr + (er - sr) * ratio)
            g = int(sg + (eg - sg) * ratio)
            b = int(sb + (eb - sb) * ratio)
            canvas.create_rectangle(0, i, width, i + 3, outline="", fill=f"#{r:02x}{g:02x}{b:02x}")

        canvas.create_polygon(0, height * 0.54, width * 0.32, height * 0.80, 0, height, fill=colors["mountain"], outline="")
        canvas.create_polygon(width, height * 0.50, width * 0.68, height * 0.80, width, height, fill=colors["mountain"], outline="")
        canvas.create_polygon(width * 0.58, height * 0.78, width, height * 0.60, width, height, width * 0.72, height, fill=colors["paper"], outline="")

        cx = width * 0.58
        cy = height * 0.45
        cube = min(width, height) * 0.26
        for pad, color in ((44, colors["line"]), (28, colors["water"]), (14, colors["accent"])):
            canvas.create_oval(cx - cube - pad, cy - cube - pad, cx + cube + pad, cy + cube + pad, outline="", fill=color, stipple="gray75")

        x0 = cx - cube / 2
        y0 = cy - cube / 2
        x1 = cx + cube / 2
        y1 = cy + cube / 2
        canvas.create_rectangle(x0, y0, x1, y1, fill=colors["accent"], outline=colors["ice"], width=1)
        canvas.create_polygon(x1, y0, x1 + cube * 0.28, y0 + cube * 0.16, x1 + cube * 0.28, y1 + cube * 0.16, x1, y1, fill=colors["water"], outline=colors["muted"])
        canvas.create_polygon(x0, y0, x1, y0, x1 + cube * 0.28, y0 + cube * 0.16, x0 + cube * 0.28, y0 + cube * 0.16, fill=colors["ice"], outline=colors["muted"])
        canvas.create_line(x0 + cube * 0.18, y0 + cube * 0.6, x1 - cube * 0.2, y0 + cube * 0.18, fill=colors["line"], width=3)

        water_y = height * 0.74
        for n in range(14):
            y = water_y + n * 7
            inset = n * 18
            color = colors["water"] if n % 2 == 0 else colors["line"]
            canvas.create_line(inset, y, width - inset, y + 2, fill=color, width=1)

        canvas.create_rectangle(1, 1, width - 2, height - 2, outline=colors["line"], width=1)
        canvas.create_text(28, 22, anchor="w", text="沉浸式视觉面板", fill=colors["ice"], font=("Microsoft YaHei UI", 10, "bold"))
        canvas.create_text(width - 28, height - 24, anchor="e", text="向下滚动配置", fill=colors["accent"], font=("Microsoft YaHei UI", 9, "bold"))

    def _apply_theme(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        colors = theme_palette(self.theme_name.get())
        self.colors = colors
        self.root.configure(bg=colors["black"])

        style.configure(".", font=("Microsoft YaHei UI", 10), borderwidth=0)
        style.configure("App.TFrame", background=colors["black"])
        style.configure("Sidebar.TFrame", background=colors["ink"])
        style.configure("Panel.TFrame", background=colors["panel"])
        style.configure("Card.TFrame", background=colors["paper"], relief="flat", borderwidth=0)
        style.configure("Footer.TFrame", background=colors["black"])
        style.configure("Scene.TFrame", background=colors["panel"])

        style.configure("Brand.TLabel", background=colors["ink"], foreground=colors["ice"], font=("Microsoft YaHei UI", 24, "bold"))
        style.configure("BrandSub.TLabel", background=colors["ink"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("NavActive.TLabel", background=colors["ink"], foreground=colors["ice"], font=("Consolas", 10, "bold"))
        style.configure("Nav.TLabel", background=colors["ink"], foreground=colors["muted"], font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Stat.TLabel", background=colors["ink"], foreground=colors["accent"], font=("Consolas", 20, "bold"))
        style.configure("StatSub.TLabel", background=colors["ink"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Eyebrow.TLabel", background=colors["panel"], foreground=colors["accent"], font=("Consolas", 9, "bold"))
        style.configure("Heading.TLabel", background=colors["panel"], foreground=colors["ice"], font=("Microsoft YaHei UI", 23, "bold"))
        style.configure("SceneTitle.TLabel", background=colors["panel"], foreground=colors["ice"], font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("SceneMeta.TLabel", background=colors["panel"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Section.TLabel", background=colors["paper"], foreground=colors["ice"], font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Field.TLabel", background=colors["paper"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("FieldPanel.TLabel", background=colors["panel"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Status.TLabel", background=colors["black"], foreground=colors["ice"], font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=colors["paper"], foreground=colors["muted"], font=("Microsoft YaHei UI", 9))

        style.configure(
            "TEntry",
            fieldbackground=colors["field"],
            foreground=colors["ice"],
            bordercolor=colors["line"],
            lightcolor=colors["line"],
            darkcolor=colors["line"],
            insertcolor=colors["ice"],
            padding=8,
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["field"],
            background=colors["field"],
            foreground=colors["ice"],
            bordercolor=colors["line"],
            arrowcolor=colors["accent"],
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["field"])],
            foreground=[("readonly", colors["ice"])],
            selectbackground=[("readonly", colors["button"])],
            selectforeground=[("readonly", colors["ice"])],
        )

        style.configure("TButton", padding=(12, 8), background=colors["button"], foreground=colors["ice"], bordercolor=colors["line"])
        style.map("TButton", background=[("active", colors["line"]), ("disabled", colors["field"])], foreground=[("disabled", colors["muted"])])
        style.configure("Primary.TButton", padding=(18, 11), background=colors["primary"], foreground=colors["primary_fg"], font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", colors["accent"]), ("disabled", colors["field"])], foreground=[("disabled", colors["muted"])])
        style.configure("Ghost.TButton", padding=(11, 8), background=colors["button"], foreground=colors["ice"], bordercolor=colors["line"])
        style.map("Ghost.TButton", background=[("active", colors["line"])])

        style.configure("TRadiobutton", background=colors["paper"], foreground=colors["ice"])
        style.map("TRadiobutton", background=[("active", colors["paper"])], foreground=[("active", colors["accent"])])
        style.map(
            "TLabel",
            background=[("disabled", colors["paper"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", colors["field"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.map(
            "TButton",
            background=[("active", colors["line"]), ("disabled", colors["field"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure("Vertical.TScrollbar", background=colors["button"], troughcolor=colors["black"], arrowcolor=colors["accent"])

        if self.scroll_canvas is not None:
            self.scroll_canvas.configure(bg=colors["panel"])
        if self.scene_canvas is not None:
            self.scene_canvas.configure(bg=colors["panel"])
            self._draw_scene()
        if self.prompt_text is not None:
            self.prompt_text.configure(
                bg=colors["field"],
                fg=colors["ice"],
                insertbackground=colors["accent"],
                selectbackground=colors["line"],
                selectforeground=colors["ice"],
            )
        if self.log_text is not None:
            self.log_text.configure(
                bg=colors["field"],
                fg=colors["ice"],
                insertbackground=colors["accent"],
                selectbackground=colors["line"],
                selectforeground=colors["ice"],
            )

    def _build_sidebar(self, sidebar: ttk.Frame) -> None:
        ttk.Label(sidebar, text="Ai炫滔", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text="生图创作系统", style="BrandSub.TLabel").pack(anchor="w", pady=(4, 24))

        ttk.Separator(sidebar).pack(fill="x", pady=(0, 22))
        ttk.Label(sidebar, text="■ 创作流程", style="NavActive.TLabel").pack(anchor="w", pady=(0, 16))
        for item in ("提示词", "原图输入", "输出设置", "生成结果", "历史记录"):
            ttk.Label(sidebar, text=f"  {item}", style="Nav.TLabel").pack(anchor="w", pady=(0, 13))

        ttk.Separator(sidebar).pack(fill="x", pady=(10, 22))
        ttk.Label(sidebar, text="图像", style="Stat.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text="生成图与记录同步保存", style="StatSub.TLabel").pack(anchor="w", pady=(0, 18))

        spacer = ttk.Frame(sidebar, style="Sidebar.TFrame")
        spacer.pack(fill=BOTH, expand=True)

        ttk.Label(sidebar, text="密钥", style="Stat.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text="仅保存在当前电脑", style="StatSub.TLabel").pack(anchor="w", pady=(0, 16))
        ttk.Button(sidebar, text="打开输出目录", command=self._open_output_dir).pack(fill="x")

    def _build_form(self, form: ttk.Frame) -> None:
        self._api_card(form)
        self._settings_card(form)
        self._prompt_card(form)
        self._edit_card(form)
        self._output_card(form)
        self._log_card(form)

    def _card(self, parent: ttk.Frame, title: str, index: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(18, 16, 18, 16))
        card.pack(fill="x", pady=(0, 14))
        card.columnconfigure(1, weight=1)

        top = ttk.Frame(card, style="Card.TFrame")
        top.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 12))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text=index, style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(top, text=title, style="Section.TLabel").grid(row=0, column=1, sticky="w")
        return card

    def _api_card(self, parent: ttk.Frame) -> None:
        card = self._card(parent, "访问密钥", "01")
        ttk.Label(card, text="密钥内容", style="Field.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(card, textvariable=self.api_key, show="*", width=46).grid(row=2, column=1, columnspan=3, sticky="ew", pady=6)

        button_row = ttk.Frame(card, style="Card.TFrame")
        button_row.grid(row=3, column=1, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(button_row, text="读取", width=8, command=self._reload_key).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="保存", width=8, command=self._save_key).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="清空", width=8, command=self._clear_key).pack(side="left")

        ttk.Label(card, text="敏感信息仅保存在当前用户环境；生成记录不会写入密钥。", style="Muted.TLabel").grid(
            row=4,
            column=1,
            columnspan=3,
            sticky="w",
            pady=(8, 0),
        )

    def _settings_card(self, parent: ttk.Frame) -> None:
        card = self._card(parent, "生成设置", "02")
        ttk.Label(card, text="模式", style="Field.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        modes_host = ttk.Frame(card, style="Card.TFrame")
        modes_host.grid(row=2, column=1, sticky="w", pady=6)
        ttk.Radiobutton(modes_host, text="文生图", variable=self.mode, value="generate", command=self._toggle_edit_fields).pack(
            side="left",
            padx=(0, 18),
        )
        ttk.Radiobutton(modes_host, text="改图", variable=self.mode, value="edit", command=self._toggle_edit_fields).pack(side="left")

        ttk.Label(card, text="尺寸", style="Field.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Combobox(card, textvariable=self.size, values=SIZES, state="readonly", width=18).grid(row=3, column=1, sticky="w", pady=6)

    def _prompt_card(self, parent: ttk.Frame) -> None:
        card = self._card(parent, "提示词", "03")
        self.prompt_text = Text(
            card,
            height=7,
            wrap="word",
            font=("Microsoft YaHei UI", 10),
            bg="#07162f",
            fg="#dbe7ff",
            insertbackground="#67e8f9",
            selectbackground="#123f7f",
            selectforeground="#ffffff",
            relief="solid",
            bd=1,
            padx=10,
            pady=10,
        )
        self.prompt_text.grid(row=2, column=0, columnspan=4, sticky="ew")

    def _edit_card(self, parent: ttk.Frame) -> None:
        self.edit_frame = self._card(parent, "改图输入", "04")
        ttk.Label(self.edit_frame, text="原图", style="Field.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(self.edit_frame, textvariable=self.image_file).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Button(self.edit_frame, text="选择", command=self._choose_image).grid(row=2, column=2, padx=(10, 0), pady=6)

        ttk.Label(self.edit_frame, text="Mask", style="Field.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(self.edit_frame, textvariable=self.mask_file).grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Button(self.edit_frame, text="选择", command=self._choose_mask).grid(row=3, column=2, padx=(10, 0), pady=6)
        ttk.Button(self.edit_frame, text="清空", command=lambda: self.mask_file.set("")).grid(row=3, column=3, padx=(8, 0), pady=6)

    def _output_card(self, parent: ttk.Frame) -> None:
        card = self._card(parent, "输出", "05")
        ttk.Label(card, text="输出目录", style="Field.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(card, textvariable=self.output_dir).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Button(card, text="选择", command=self._choose_output_dir).grid(row=2, column=2, padx=(10, 0), pady=6)

        ttk.Label(card, text="文件名", style="Field.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(card, textvariable=self.filename).grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Button(card, text="打开图片", command=self._open_image).grid(row=3, column=2, padx=(10, 0), pady=6)

    def _log_card(self, parent: ttk.Frame) -> None:
        card = self._card(parent, "日志统计", "06")
        card.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=1)

        ttk.Label(card, textvariable=self.success_count, style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Label(card, textvariable=self.failure_count, style="Section.TLabel").grid(row=2, column=1, sticky="w", pady=(0, 8))
        ttk.Button(card, text="清理日志", command=self._clear_logs).grid(row=2, column=2, sticky="e", pady=(0, 8))

        ttk.Label(card, textvariable=self.log_summary, style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.log_text = Text(
            card,
            height=6,
            wrap="word",
            font=("Microsoft YaHei UI", 9),
            bg=self.colors["field"],
            fg=self.colors["ice"],
            insertbackground=self.colors["accent"],
            selectbackground=self.colors["line"],
            selectforeground=self.colors["ice"],
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
        )
        self.log_text.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.log_text.configure(state=DISABLED)

    def _build_footer(self, workspace: ttk.Frame) -> None:
        bottom = ttk.Frame(workspace, style="Footer.TFrame", padding=(22, 14, 22, 14))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)

        self.generate_button = ttk.Button(bottom, text="开始生成", style="Primary.TButton", command=self._start_generation)
        self.generate_button.grid(row=0, column=0, sticky="w", padx=(0, 14))
        ttk.Label(bottom, textvariable=self.status, style="Status.TLabel", wraplength=660).grid(row=0, column=1, sticky="ew")

    def _toggle_edit_fields(self) -> None:
        is_edit = self.mode.get() == "edit"
        if is_edit:
            self.size.set("auto")
        state = NORMAL if is_edit else DISABLED
        for child in self.edit_frame.winfo_children():
            try:
                child.configure(state=state)
            except Exception:
                pass

    def _prompt(self) -> str:
        return self.prompt_text.get("1.0", END).strip()

    def _read_logs(self) -> list[dict]:
        path = log_path()
        if not path.exists():
            return []
        items: list[dict] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                items.append(data)
        return items

    def _append_log(self, event: str, message: str, image_path: Path | None = None) -> None:
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "mode": self.mode.get(),
            "size": self.size.get(),
            "message": message,
        }
        if image_path is not None:
            record["image_path"] = str(image_path)
        path = log_path()
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._refresh_log_view()

    def _refresh_log_view(self) -> None:
        logs = self._read_logs()
        success = sum(1 for item in logs if item.get("event") == "success")
        failure = sum(1 for item in logs if item.get("event") == "failure")
        self.success_count.set(f"成功 {success} 张")
        self.failure_count.set(f"失败 {failure} 张")
        self.log_summary.set(f"日志位置：{log_path()}" if logs else "暂无生成日志")

        if self.log_text is None:
            return
        recent = logs[-20:]
        lines = []
        event_name = {"start": "开始", "success": "成功", "failure": "失败"}
        for item in reversed(recent):
            name = event_name.get(str(item.get("event")), str(item.get("event") or "记录"))
            message = str(item.get("message") or "")
            lines.append(f"{item.get('time', '')}  {name}  {message}")
        self.log_text.configure(state=NORMAL)
        self.log_text.delete("1.0", END)
        self.log_text.insert("1.0", "\n".join(lines) if lines else "暂无日志")
        self.log_text.configure(state=DISABLED)

    def _clear_logs(self) -> None:
        path = log_path()
        if path.exists():
            path.unlink()
        self.status.set("已清理生成日志。")
        self._refresh_log_view()

    def _reload_key(self) -> None:
        self.api_key.set(load_env_key())
        self.status.set("已读取本机保存的密钥。")

    def _save_key(self) -> None:
        try:
            save_user_env_key(self.api_key.get())
            messagebox.showinfo(APP_TITLE, "已保存到当前用户环境。新打开的程序也能读取。")
        except Image2Error as error:
            messagebox.showerror(APP_TITLE, str(error))

    def _clear_key(self) -> None:
        try:
            clear_user_env_key()
            self.api_key.set("")
            self.status.set("已清空本机保存的密钥。")
            messagebox.showinfo(APP_TITLE, "已从当前用户环境中删除本机密钥。")
        except Image2Error as error:
            messagebox.showerror(APP_TITLE, str(error))

    def _choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录", initialdir=self.output_dir.get() or str(Path.cwd()))
        if path:
            self.output_dir.set(path)

    def _choose_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择原图",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp"), ("All files", "*.*")],
        )
        if path:
            self.image_file.set(path)

    def _choose_mask(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Mask",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp"), ("All files", "*.*")],
        )
        if path:
            self.mask_file.set(path)

    def _reset_filename(self) -> None:
        self.filename.set(f"image2_{timestamp()}.png")

    def _start_generation(self) -> None:
        if violates_local_safety(self._prompt()):
            self._generation_failed(LOCAL_SAFETY_MESSAGE)
            return
        self.generate_button.configure(state=DISABLED)
        self.status.set("正在调用 image2，请稍等...")
        self._append_log("start", f"开始生成：{ensure_png_name(self.filename.get())}")
        thread = threading.Thread(target=self._generate_worker, daemon=True)
        thread.start()

    def _generate_worker(self) -> None:
        try:
            mode = self.mode.get()
            if mode == "edit":
                result = edit_image(
                    self.api_key.get(),
                    self._prompt(),
                    self.size.get(),
                    Path(self.output_dir.get()),
                    self.filename.get(),
                    Path(self.image_file.get()),
                    Path(self.mask_file.get()) if self.mask_file.get().strip() else None,
                )
            else:
                result = generate_image(
                    self.api_key.get(),
                    self._prompt(),
                    self.size.get(),
                    Path(self.output_dir.get()),
                    self.filename.get(),
                )
            self.last_image_path = result.image_path
            self.root.after(0, self._generation_done, result)
        except Exception as error:
            self.root.after(0, self._generation_failed, str(error))

    def _generation_done(self, result: GenerationResult) -> None:
        self.generate_button.configure(state=NORMAL)
        self.status.set(f"生成成功：{result.image_path}")
        self._append_log("success", f"生成成功：{result.image_path.name}", result.image_path)
        messagebox.showinfo(APP_TITLE, f"生成成功：\n{result.image_path}")

    def _generation_failed(self, message: str) -> None:
        self.generate_button.configure(state=NORMAL)
        self.status.set(f"生成失败：{message}")
        self._append_log("failure", f"生成失败：{message}")
        messagebox.showerror(APP_TITLE, message)

    def _open_image(self) -> None:
        if self.last_image_path and self.last_image_path.exists():
            os.startfile(self.last_image_path)
        else:
            messagebox.showwarning(APP_TITLE, "还没有可打开的生成图片。")

    def _open_output_dir(self) -> None:
        path = Path(self.output_dir.get())
        if path.exists():
            os.startfile(path)
        else:
            messagebox.showwarning(APP_TITLE, "输出目录不存在。")

    def run(self) -> None:
        self.root.mainloop()


def self_test() -> int:
    checks = {
        "python": sys.version.split()[0],
        "tkinter": "ok",
        "curl": find_curl(),
        "asset_root": str(app_root()),
        "icon": str(asset_path("assets", "xuantao.ico")),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


def edit_smoke_test() -> int:
    api_key = load_env_key()
    if not api_key:
        print("NO_KEY", file=sys.stderr)
        return 2

    image_file = Path.home() / "Desktop" / "test.png"
    if not image_file.exists():
        print(f"NO_IMAGE {image_file}", file=sys.stderr)
        return 3

    result = edit_image(
        api_key=api_key,
        prompt="\u4e0d\u6539\u53d8\u56fe\u7247\u7ed3\u6784\uff0c\u751f\u6210\u5bf9\u5e94\u5b9e\u666f\u56fe\u7247",
        size="auto",
        output_dir=writable_app_dir(),
        filename=f"exe_edit_smoke_{timestamp()}.png",
        image_file=image_file,
        mask_file=None,
    )
    print(json.dumps(
        {
            "image_path": str(result.image_path),
            "image_size": result.image_path.stat().st_size,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if "--edit-smoke-test" in sys.argv:
        return edit_smoke_test()
    if not acquire_single_instance_lock():
        messagebox.showwarning(APP_TITLE, "生图工具已经在运行，请先关闭旧窗口后再打开。")
        return 1
    app = Image2App()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
