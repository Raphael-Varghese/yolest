import os
import json
import re
import uuid
import ast
import math
import random
import operator
import subprocess
import threading
import base64
import time
import hashlib
import secrets
import requests
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_socketio import SocketIO, emit
from llama_cpp import Llama

# Try to import PIL for image generation
PIL_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    pass


# -- Custom password hashing (no external dependency) --
def _generate_password_hash(password):
    salt = secrets.token_hex(16)
    iterations = 100000
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('ascii'), iterations)
    return f"pbkdf2:sha256:{iterations}${salt}${pw_hash.hex()}"

def _check_password_hash(stored_hash, password):
    if not stored_hash or '$' not in stored_hash:
        return False
    parts = stored_hash.split('$')
    if len(parts) != 3:
        return False
    method_part, salt, hash_value = parts
    method_bits = method_part.split(':')
    if len(method_bits) < 3:
        return False
    iterations = int(method_bits[2])
    hash_name = method_bits[1] if len(method_bits) > 1 else 'sha256'
    pw_hash = hashlib.pbkdf2_hmac(hash_name, password.encode('utf-8'), salt.encode('ascii'), iterations)
    return secrets.compare_digest(pw_hash.hex(), hash_value)

app = Flask(__name__)
app.config["SECRET_KEY"] = "yolest-secret-key-change-me"
app.config["SESSION_PERMANENT"] = False

import flask.cli
flask.cli.show_server_banner = lambda *args, **kwargs: None
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# -- Paths --
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = str(BASE_DIR / "model.gguf")
CHATS_DIR = BASE_DIR / "chats"
CHATS_DIR.mkdir(exist_ok=True)
WORKSPACE = BASE_DIR / "workspace"
WORKSPACE.mkdir(exist_ok=True)
AGENTS_DIR = WORKSPACE / "agents"
AGENTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR = WORKSPACE / "images"
IMAGES_DIR.mkdir(exist_ok=True)
LOGINS_FILE = BASE_DIR / "logins.txt"
SYSTEM_PROMPT_FILE = BASE_DIR / "system_prompt.txt"
README_FILE = BASE_DIR / "README.md"
if not README_FILE.exists():
    README_FILE = BASE_DIR / "readme.md"
if not README_FILE.exists():
    README_FILE = BASE_DIR / "README.txt"

# -- Config --
N_THREADS = 8
N_CTX = 4096
N_BATCH = 512
MAX_TOKENS = 1024
MAX_HISTORY_TURNS = 6
MAX_TOOL_ROUNDS = 5
MAX_TOOL_RESULT_CHARS = 4500
REQUIRED_API_KEY = "yolest-live:ocDZAfRjxQyiWn4rXuT7JPSLqYOdkaVN"

# -- Ollama Cloud Config --
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
OLLAMA_BASE_URL = "https://ollama.com/api"
OLLAMA_MODELS = [
    "gpt-oss:120b-cloud",
    "gemma4:31b-cloud",
]
OLLAMA_HEADERS = {
    "Authorization": f"Bearer {OLLAMA_API_KEY}",
    "Content-Type": "application/json",
}

# -- Load System Prompt from file --
def load_system_prompt():
    if SYSTEM_PROMPT_FILE.exists():
        return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    return "You are YOLEST, a helpful AI assistant with access to tools."

def save_system_prompt(text):
    SYSTEM_PROMPT_FILE.write_text(text, encoding="utf-8")

SYSTEM_PROMPT = load_system_prompt()

# -- Load model (optional for deployment) --
llm = None
LOCAL_MODEL_AVAILABLE = False
if MODEL_PATH.exists():
    try:
        print("[YOLEST] Loading local model...")
        llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=N_CTX,
            n_threads=N_THREADS,
            n_threads_batch=N_THREADS,
            n_batch=N_BATCH,
            verbose=False
        )
        LOCAL_MODEL_AVAILABLE = True
        print("[YOLEST] Local model loaded!")
    except Exception as e:
        print(f"[YOLEST] Local model failed to load: {e}")
else:
    print("[YOLEST] No local model found at", MODEL_PATH)
    print("[YOLEST] Cloud-only mode. Local models disabled.")

# -- In-memory session store --
active_chats = {}
stop_events = {}

# -- Auth / User Management --
# Format: username|fullname|password_hash|role|api_key|has_api_key
# role: dev_admin, admin, user

def load_users():
    users = {}
    if not LOGINS_FILE.exists():
        return users
    for line in LOGINS_FILE.read_text(encoding="utf-8").strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) >= 6:
            users[parts[0]] = {
                "username": parts[0],
                "fullname": parts[1],
                "password_hash": parts[2],
                "role": parts[3],
                "api_key": parts[4],
                "has_api_key": parts[5].lower() == "true"
            }
    return users

def save_users(users_dict):
    lines = ["# format: username|fullname|password_hash|role|api_key|has_api_key"]
    for u in users_dict.values():
        lines.append(f"{u['username']}|{u['fullname']}|{u['password_hash']}|{u['role']}|{u['api_key']}|{str(u.get('has_api_key', False)).lower()}")
    LOGINS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def init_admins():
    users = load_users()
    changed = False
    if "raphaelv" not in users:
        users["raphaelv"] = {
            "username": "raphaelv",
            "fullname": "Raphael Varghese",
            "password_hash": "pbkdf2:sha256:100000$21769a32a87ad15ff574e5d8118f0b29$3daf1c19bad652a7cc0d075c1ffb0c161ff8524c2c1f628ee76e143b17877078",
            "role": "dev_admin",
            "api_key": REQUIRED_API_KEY,
            "has_api_key": True
        }
        changed = True
    if "saip" not in users:
        users["saip"] = {
            "username": "saip",
            "fullname": "Sai Peddada",
            "password_hash": "pbkdf2:sha256:100000$92969b3112b3012a0700a8f882952351$87083d2facb4b2de21acb9611968562f96220f2b857d649cfc6319417510cb91",
            "role": "admin",
            "api_key": REQUIRED_API_KEY,
            "has_api_key": True
        }
        changed = True
    if changed:
        save_users(users)
        print("[YOLEST] Admin accounts initialized.")

init_admins()

# -- Ollama Cloud Helper --

def test_ollama_model(model_name):
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "stream": False,
        "options": {"temperature": 0.7},
    }
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/chat",
            headers=OLLAMA_HEADERS,
            json=payload,
            timeout=90,
        )
        if r.status_code == 200:
            return True, r.json()["message"]["content"]
        else:
            return False, f"HTTP {r.status_code} | {r.text}"
    except Exception as e:
        return False, str(e)

def send_ollama_message(model_name, messages):
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7},
    }
    r = requests.post(
        f"{OLLAMA_BASE_URL}/chat",
        headers=OLLAMA_HEADERS,
        json=payload,
        timeout=120,
    )
    return r

def get_working_ollama_model():
    for m in OLLAMA_MODELS:
        ok, _ = test_ollama_model(m)
        if ok:
            return m
    return None

# -- Math Eval --
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow
}
_UOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log, "log10": math.log10, "exp": math.exp,
    "factorial": math.factorial, "floor": math.floor, "ceil": math.ceil
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}

def _eval_math(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UOPS:
        return _UOPS[type(node.op)](_eval_math(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left = _eval_math(node.left)
        right = _eval_math(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 10000:
            raise ValueError("Exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval_math(arg) for arg in node.args])
    raise ValueError("Unsupported expression")

def calculator(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 500:
        raise ValueError("Invalid expression")
    return str(_eval_math(ast.parse(expression, mode="eval").body))

# -- Web Tools --
def _fetch_html(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")

def _parse_bing_results(html, max_results):
    import re, base64, urllib.parse
    results = []
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL | re.IGNORECASE)
    for block in blocks[:max_results]:
        a_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL | re.IGNORECASE)
        if not a_match:
            continue
        href = a_match.group(1)
        if '/ck/a?' in href:
            u_match = re.search(r'[?&]u=([^&]+)', href)
            if u_match:
                try:
                    encoded = u_match.group(1)
                    if encoded.startswith('a1'):
                        encoded = encoded[2:]
                    decoded = base64.urlsafe_b64decode(encoded + '==').decode('utf-8', errors='ignore')
                    if decoded.startswith('http'):
                        href = decoded
                except Exception:
                    pass
        title = re.sub(r'<[^>]+>', '', a_match.group(2)).strip()
        p_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL | re.IGNORECASE)
        snippet = re.sub(r'<[^>]+>', '', p_match.group(1)).strip() if p_match else ""
        results.append({"title": title or "Result", "url": href, "content": snippet[:1800]})
    return results

def _parse_yahoo_results(html, max_results):
    import re
    results = []
    blocks = re.findall(r'<div class="(?:algo|srpresult)\b[^>]*>(.*?)</div>\s*</div>\s*</div>\s*</div>\s*</li>', html, re.DOTALL | re.IGNORECASE)
    if not blocks:
        blocks = re.findall(r'<div class="result\b[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL | re.IGNORECASE)
    for block in blocks[:max_results]:
        a_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL | re.IGNORECASE)
        if not a_match:
            continue
        href = a_match.group(1)
        title = re.sub(r'<[^>]+>', '', a_match.group(2)).strip()
        span_match = re.search(r'<span class="(?:fc-falcon|s-prod-color)\b[^>]*>(.*?)</span>', block, re.DOTALL | re.IGNORECASE)
        snippet = re.sub(r'<[^>]+>', '', span_match.group(1)).strip() if span_match else ""
        results.append({"title": title or "Result", "url": href, "content": snippet[:1800]})
    return results

def web_search(query, max_results=3):
    import urllib.parse, urllib.request
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query is empty")
    max_results = max(1, min(int(max_results), 10))
    errors = []

    try:
        title = query.strip().replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
        req = urllib.request.Request(url, headers={"User-Agent": "YOLEST/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("title") and data.get("extract"):
            return json.dumps([{
                "title": data.get("title", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "content": data.get("extract", "")[:1800]
            }], ensure_ascii=False)
    except Exception as e:
        errors.append(f"Wikipedia summary: {e}")

    try:
        url = (
            "https://en.wikipedia.org/w/api.php?"
            f"action=opensearch&search={urllib.parse.quote(query)}"
            f"&limit={max_results}&namespace=0&format=json"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "YOLEST/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        titles = data[1] if len(data) > 1 else []
        descriptions = data[2] if len(data) > 2 else []
        urls = data[3] if len(data) > 3 else []
        results = []
        for i in range(min(len(titles), max_results)):
            results.append({
                "title": titles[i],
                "url": urls[i] if i < len(urls) else "",
                "content": descriptions[i][:1800] if i < len(descriptions) else ""
            })
        if results:
            return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        errors.append(f"Wikipedia OpenSearch: {e}")

    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        html = _fetch_html(url, timeout=15)
        results = _parse_bing_results(html, max_results)
        if results:
            return json.dumps(results, ensure_ascii=False)
        errors.append("Bing: no results parsed")
    except Exception as e:
        errors.append(f"Bing: {e}")

    try:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"
        html = _fetch_html(url, timeout=15)
        results = _parse_yahoo_results(html, max_results)
        if results:
            return json.dumps(results, ensure_ascii=False)
        errors.append("Yahoo: no results parsed")
    except Exception as e:
        errors.append(f"Yahoo: {e}")

    raise RuntimeError("All search sources failed. Details: " + " | ".join(errors))

def web_read(url):
    import urllib.parse, urllib.request, base64
    if not isinstance(url, str) or not re.match(r"^https?://", url, re.I):
        raise ValueError("Only HTTP and HTTPS URLs are allowed")
    if '/ck/a?' in url:
        u_match = re.search(r'[?&]u=([^&]+)', url)
        if u_match:
            try:
                encoded = u_match.group(1)
                if encoded.startswith('a1'):
                    encoded = encoded[2:]
                decoded = base64.urlsafe_b64decode(encoded + '==').decode('utf-8', errors='ignore')
                if decoded.startswith('http'):
                    url = decoded
            except Exception:
                pass
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        html = response.read().decode("utf-8", errors="ignore")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ""
    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return json.dumps([{"title": title, "url": url, "content": text[:3000]}], ensure_ascii=False)

def weather(location):
    import urllib.parse, urllib.request
    if not isinstance(location, str) or not location.strip():
        raise ValueError("Location is empty")
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(location)}&count=1"
    req = urllib.request.Request(geo_url, headers={"User-Agent": "YOLEST/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        geo_data = json.loads(response.read().decode("utf-8"))
    if not geo_data.get("results"):
        raise ValueError(f"Location not found: {location}")
    result = geo_data["results"][0]
    lat = result["latitude"]
    lon = result["longitude"]
    name = result["name"]
    country = result.get("country", "")
    admin1 = result.get("admin1", "")
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        f"&timezone=auto"
    )
    req = urllib.request.Request(weather_url, headers={"User-Agent": "YOLEST/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        weather_data = json.loads(response.read().decode("utf-8"))
    current = weather_data.get("current", {})
    wmo_codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        56: "Light freezing drizzle", 57: "Dense freezing drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        66: "Light freezing rain", 67: "Heavy freezing rain",
        71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
        77: "Snow grains",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        85: "Slight snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
    }
    code = current.get("weather_code")
    condition = wmo_codes.get(code, "Unknown") if code is not None else "Unknown"
    display_name = f"{name}, {admin1}" if admin1 else name
    if country:
        display_name += f", {country}"
    return json.dumps({
        "location": display_name,
        "latitude": lat, "longitude": lon,
        "temperature_c": current.get("temperature_2m"),
        "temperature_f": round(current.get("temperature_2m", 0) * 9 / 5 + 32, 1) if current.get("temperature_2m") is not None else None,
        "feels_like_c": current.get("apparent_temperature"),
        "feels_like_f": round(current.get("apparent_temperature", 0) * 9 / 5 + 32, 1) if current.get("apparent_temperature") is not None else None,
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "condition": condition,
        "weather_code": code
    }, ensure_ascii=False)

def python_sandbox(code):
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Python code is empty")
    if len(code) > 12000:
        raise ValueError("Python code is too long")
    script_path = WORKSPACE / f"script_{uuid.uuid4().hex[:8]}.py"
    script_path.write_text(code, encoding="utf-8")
    result = subprocess.run(
        ["powershell", "-Command", f"python '{script_path}'"],
        capture_output=True, text=True, timeout=20, cwd=str(WORKSPACE)
    )
    return json.dumps({"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}, ensure_ascii=False)

def current_time():
    now = datetime.now().astimezone()
    return json.dumps({"iso": now.isoformat(), "display": now.strftime("%A, %B %d, %Y %I:%M:%S %p %Z")}, ensure_ascii=False)

def create_agent(name, code):
    if not isinstance(name, str):
        raise ValueError(f"Invalid agent name type: {type(name).__name__}. Must be a string.")
    name = name.strip()
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid agent name: '{name}'. Use letters, numbers, and underscores only. Must start with a letter or underscore.")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Agent code cannot be empty")
    if len(code) > 30000:
        raise ValueError("Agent code is too long (max 30,000 chars)")

    AGENTS_DIR.mkdir(exist_ok=True)
    script_path = AGENTS_DIR / f"{name}.py"

    header = f"# YOLEST Agent: {name}\n# Created: {datetime.now().isoformat()}\n\n"
    script_path.write_text(header + code, encoding="utf-8")

    return json.dumps({"status": "created", "name": name, "path": str(script_path)}, ensure_ascii=False)

def run_saved_agent(name, input_data=None):
    script_path = AGENTS_DIR / f"{name}.py"
    if not script_path.exists():
        raise ValueError(f"Agent '{name}' not found. Create it first with create_agent.")

    input_path = None
    if input_data is not None:
        input_path = WORKSPACE / f"agent_input_{uuid.uuid4().hex[:8]}.json"
        if isinstance(input_data, str):
            try:
                json.loads(input_data)
                input_path.write_text(input_data, encoding="utf-8")
            except (json.JSONDecodeError, TypeError):
                input_path.write_text(json.dumps({"input": input_data}, ensure_ascii=False), encoding="utf-8")
        else:
            input_path.write_text(json.dumps(input_data, ensure_ascii=False), encoding="utf-8")

    try:
        if input_path:
            cmd = f"python '{script_path}' '{input_path}'"
        else:
            cmd = f"python '{script_path}'"

        result = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE)
        )

        return json.dumps({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }, ensure_ascii=False)
    finally:
        if input_path:
            input_path.unlink(missing_ok=True)

# -- Image Tools --

def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def generate_image(prompt, width=512, height=512, style="default"):
    if not PIL_AVAILABLE:
        raise RuntimeError("PIL (Pillow) is not installed. Install it with: pip install Pillow")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Image prompt is empty")
    width = max(64, min(int(width), 1024))
    height = max(64, min(int(height), 1024))

    img_id = f"gen_{uuid.uuid4().hex[:12]}"
    img_path = IMAGES_DIR / f"{img_id}.png"

    palettes = {
        "default": [("#1a1a2e", "#16213e"), ("#0f3460", "#e94560")],
        "nature": [("#2d6a4f", "#40916c"), ("#52b788", "#74c69d")],
        "sunset": [("#ff6b6b", "#feca57"), ("#ff9ff3", "#54a0ff")],
        "ocean": [("#006ba6", "#0496ff"), ("#1b4965", "#cae9ff")],
        "cyberpunk": [("#f72585", "#7209b7"), ("#3a0ca3", "#4361ee")],
        "pastel": [("#ffc8dd", "#ffafcc"), ("#bde0fe", "#a2d2ff")],
        "monochrome": [("#212529", "#495057"), ("#343a40", "#adb5bd")],
    }

    style_key = style.lower() if style.lower() in palettes else "default"
    palette = palettes[style_key]

    img = Image.new("RGB", (width, height), (20, 20, 30))
    draw = ImageDraw.Draw(img)

    c1, c2 = palette[0]
    c1_rgb = _hex_to_rgb(c1)
    c2_rgb = _hex_to_rgb(c2)

    for y in range(height):
        ratio = y / height
        r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
        g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
        b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    prompt_lower = prompt.lower()
    keywords = {
        "circle": "ellipse", "round": "ellipse", "sphere": "ellipse",
        "square": "rectangle", "box": "rectangle",
        "triangle": "polygon", "star": "star", "heart": "heart",
        "line": "lines", "wave": "waves", "dot": "dots",
    }
    shapes = []
    for word, shape in keywords.items():
        if word in prompt_lower and shape not in shapes:
            shapes.append(shape)
    if not shapes:
        shapes = ["ellipse", "rectangle", "lines"]

    rng = random.Random(hash(prompt) % (2**32))

    for shape in shapes[:3]:
        fc = _hex_to_rgb(rng.choice(palette)[0])
        for _ in range(rng.randint(3, 10)):
            sx = rng.randint(0, width)
            sy = rng.randint(0, height)
            sw = rng.randint(30, width // 3)
            sh = rng.randint(30, height // 3)
            oc = (rng.randint(100, 255), rng.randint(100, 255), rng.randint(100, 255))

            if shape == "ellipse":
                draw.ellipse([sx, sy, sx+sw, sy+sh], fill=fc, outline=oc)
            elif shape == "rectangle":
                draw.rectangle([sx, sy, sx+sw, sy+sh], fill=fc, outline=oc)
            elif shape == "polygon":
                pts = [(sx + rng.randint(-sw, sw), sy + rng.randint(-sh, sh)) for _ in range(3)]
                draw.polygon(pts, fill=fc, outline=oc)
            elif shape == "star":
                cx, cy, r = sx + sw//2, sy + sh//2, min(sw, sh)//2
                star_pts = []
                for i in range(10):
                    angle = math.pi / 2 + i * math.pi / 5
                    rad = r if i % 2 == 0 else r // 2
                    star_pts.append((cx + rad * math.cos(angle), cy - rad * math.sin(angle)))
                draw.polygon(star_pts, fill=fc, outline=oc)
            elif shape == "heart":
                cx, cy, r = sx + sw//2, sy + sh//2, min(sw, sh)//3
                pts = []
                for t in range(100):
                    t_val = t / 100.0 * 2 * math.pi
                    hx = cx + r * 0.5 * (16 * math.sin(t_val)**3)
                    hy = cy - r * 0.5 * (13 * math.cos(t_val) - 5 * math.cos(2*t_val) - 2 * math.cos(3*t_val) - math.cos(4*t_val))
                    pts.append((hx / 16 + cx * 0.5, hy / 16 + cy * 0.5))
                if pts:
                    draw.polygon(pts, fill=fc)
            elif shape == "lines":
                draw.line([(sx, sy), (sx+sw, sy+sh)], fill=oc, width=rng.randint(1, 3))
            elif shape == "waves":
                for i in range(3):
                    yb = sy + i * (sh // 3)
                    wpts = [(x, yb + int(8 * math.sin(x / 15))) for x in range(sx, sx+sw, 4)]
                    if len(wpts) > 1:
                        draw.line(wpts, fill=oc, width=2)
            elif shape == "dots":
                for _ in range(rng.randint(8, 20)):
                    dx, dy = sx + rng.randint(0, sw), sy + rng.randint(0, sh)
                    dr = rng.randint(2, 5)
                    draw.ellipse([dx-dr, dy-dr, dx+dr, dy+dr], fill=oc)

    img = img.filter(ImageFilter.GaussianBlur(radius=0.3))

    try:
        font_size = max(10, min(20, width // 45))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        text = f"YOLEST: {prompt[:55]}"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        tx = (width - text_w) // 2
        ty = height - font_size - 12
        draw.rectangle([tx - 6, ty - 3, tx + text_w + 6, ty + font_size + 3], fill=(0, 0, 0))
        draw.text((tx, ty), text, fill=(255, 255, 255), font=font)
    except Exception:
        pass

    img.save(img_path, "PNG")
    img_url = f"/api/images/{img_id}.png"

    return json.dumps({
        "image_id": img_id,
        "prompt": prompt,
        "width": width,
        "height": height,
        "style": style_key,
        "url": img_url,
        "message": f"Generated {width}x{height} image in '{style_key}' style."
    }, ensure_ascii=False)



def generate_image_base64(prompt, width=512, height=512, style="default"):
    """Generate an abstract procedural image and return as base64 data URI."""
    if not PIL_AVAILABLE:
        raise RuntimeError("PIL (Pillow) is not installed. Install it with: pip install Pillow")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Image prompt is empty")
    width = max(64, min(int(width), 1024))
    height = max(64, min(int(height), 1024))

    palettes = {
        "default": [("#1a1a2e", "#16213e"), ("#0f3460", "#e94560")],
        "nature": [("#2d6a4f", "#40916c"), ("#52b788", "#74c69d")],
        "sunset": [("#ff6b6b", "#feca57"), ("#ff9ff3", "#54a0ff")],
        "ocean": [("#006ba6", "#0496ff"), ("#1b4965", "#cae9ff")],
        "cyberpunk": [("#f72585", "#7209b7"), ("#3a0ca3", "#4361ee")],
        "pastel": [("#ffc8dd", "#ffafcc"), ("#bde0fe", "#a2d2ff")],
        "monochrome": [("#212529", "#495057"), ("#343a40", "#adb5bd")],
    }

    style_key = style.lower() if style.lower() in palettes else "default"
    palette = palettes[style_key]

    img = Image.new("RGB", (width, height), (20, 20, 30))
    draw = ImageDraw.Draw(img)

    c1, c2 = palette[0]
    c1_rgb = _hex_to_rgb(c1)
    c2_rgb = _hex_to_rgb(c2)

    for y in range(height):
        ratio = y / height
        r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
        g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
        b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    prompt_lower = prompt.lower()
    keywords = {
        "circle": "ellipse", "round": "ellipse", "sphere": "ellipse",
        "square": "rectangle", "box": "rectangle",
        "triangle": "polygon", "star": "star", "heart": "heart",
        "line": "lines", "wave": "waves", "dot": "dots",
    }
    shapes = []
    for word, shape in keywords.items():
        if word in prompt_lower and shape not in shapes:
            shapes.append(shape)
    if not shapes:
        shapes = ["ellipse", "rectangle", "lines"]

    rng = random.Random(hash(prompt) % (2**32))

    for shape in shapes[:3]:
        fc = _hex_to_rgb(rng.choice(palette)[0])
        for _ in range(rng.randint(3, 10)):
            sx = rng.randint(0, width)
            sy = rng.randint(0, height)
            sw = rng.randint(30, width // 3)
            sh = rng.randint(30, height // 3)
            oc = (rng.randint(100, 255), rng.randint(100, 255), rng.randint(100, 255))

            if shape == "ellipse":
                draw.ellipse([sx, sy, sx+sw, sy+sh], fill=fc, outline=oc)
            elif shape == "rectangle":
                draw.rectangle([sx, sy, sx+sw, sy+sh], fill=fc, outline=oc)
            elif shape == "polygon":
                pts = [(sx + rng.randint(-sw, sw), sy + rng.randint(-sh, sh)) for _ in range(3)]
                draw.polygon(pts, fill=fc, outline=oc)
            elif shape == "star":
                cx, cy, r = sx + sw//2, sy + sh//2, min(sw, sh)//2
                star_pts = []
                for i in range(10):
                    angle = math.pi / 2 + i * math.pi / 5
                    rad = r if i % 2 == 0 else r // 2
                    star_pts.append((cx + rad * math.cos(angle), cy - rad * math.sin(angle)))
                draw.polygon(star_pts, fill=fc, outline=oc)
            elif shape == "heart":
                cx, cy, r = sx + sw//2, sy + sh//2, min(sw, sh)//3
                pts = []
                for t in range(100):
                    t_val = t / 100.0 * 2 * math.pi
                    hx = cx + r * 0.5 * (16 * math.sin(t_val)**3)
                    hy = cy - r * 0.5 * (13 * math.cos(t_val) - 5 * math.cos(2*t_val) - 2 * math.cos(3*t_val) - math.cos(4*t_val))
                    pts.append((hx / 16 + cx * 0.5, hy / 16 + cy * 0.5))
                if pts:
                    draw.polygon(pts, fill=fc)
            elif shape == "lines":
                draw.line([(sx, sy), (sx+sw, sy+sh)], fill=oc, width=rng.randint(1, 3))
            elif shape == "waves":
                for i in range(3):
                    yb = sy + i * (sh // 3)
                    wpts = [(x, yb + int(8 * math.sin(x / 15))) for x in range(sx, sx+sw, 4)]
                    if len(wpts) > 1:
                        draw.line(wpts, fill=oc, width=2)
            elif shape == "dots":
                for _ in range(rng.randint(8, 20)):
                    dx, dy = sx + rng.randint(0, sw), sy + rng.randint(0, sh)
                    dr = rng.randint(2, 5)
                    draw.ellipse([dx-dr, dy-dr, dx+dr, dy+dr], fill=oc)

    img = img.filter(ImageFilter.GaussianBlur(radius=0.3))

    try:
        font_size = max(10, min(20, width // 45))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        text = f"YOLEST: {prompt[:55]}"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        tx = (width - text_w) // 2
        ty = height - font_size - 12
        draw.rectangle([tx - 6, ty - 3, tx + text_w + 6, ty + font_size + 3], fill=(0, 0, 0))
        draw.text((tx, ty), text, fill=(255, 255, 255), font=font)
    except Exception:
        pass

    # Convert to base64 data URI
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64}"

    return json.dumps({
        "data_uri": data_uri,
        "prompt": prompt,
        "width": width,
        "height": height,
        "style": style_key,
        "message": f"Generated {width}x{height} image in '{style_key}' style as base64 data URI."
    }, ensure_ascii=False)

def view_image(image_id_or_url):
    if not isinstance(image_id_or_url, str) or not image_id_or_url.strip():
        raise ValueError("Image ID or URL is empty")
    img_id = image_id_or_url.strip().split("/")[-1]
    if not img_id.endswith(".png"):
        img_id += ".png"
    img_path = IMAGES_DIR / img_id
    if not img_path.exists():
        raise ValueError(f"Image not found: {img_id}")
    return json.dumps({
        "image_id": img_id.replace(".png", ""),
        "url": f"/api/images/{img_id}",
        "message": f"Image available at /api/images/{img_id}"
    }, ensure_ascii=False)


def list_images():
    images = []
    for f in sorted(IMAGES_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
        images.append({
            "id": f.stem,
            "filename": f.name,
            "url": f"/api/images/{f.name}",
            "size": f.stat().st_size,
            "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        })
    return json.dumps({"count": len(images), "images": images}, ensure_ascii=False)


def execute_tool(name, args):
    if name == "web_search":
        return web_search(args.get("query", ""), args.get("max_results", 3))
    if name == "web_read":
        return web_read(args.get("url", ""))
    if name == "weather":
        return weather(args.get("location", ""))
    if name == "python_sandbox":
        return python_sandbox(args.get("code", ""))
    if name == "calculator":
        return calculator(args.get("expression", ""))
    if name == "current_time":
        return current_time()
    if name == "create_agent":
        return create_agent(args.get("name", ""), args.get("code", ""))
    if name == "run_agent":
        return run_saved_agent(args.get("name", ""), args.get("input"))
    if name == "generate_image":
        prompt = args.get("prompt") or args.get("description", "")
        return generate_image(prompt, args.get("width", 512), args.get("height", 512), args.get("style", "default"))
    if name == "generate_image_base64":
        prompt = args.get("prompt") or args.get("description", "")
        return generate_image_base64(prompt, args.get("width", 512), args.get("height", 512), args.get("style", "default"))
    if name == "view_image":
        return view_image(args.get("image_id", ""))
    if name == "list_images":
        return list_images()
    raise ValueError(f"Unknown tool: {name}")

def extract_tool_call(text):
    if not text:
        return None

    cleaned = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text).strip()
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
    cleaned = cleaned.replace("```", "").strip()
    cleaned = cleaned.replace('\\"', '"')
    cleaned = re.sub(r'\{tool_call\s*:', '{"tool_call":', cleaned)

    valid_tools = {"web_search", "web_read", "weather", "python_sandbox", "calculator", "current_time", "create_agent", "run_agent", "generate_image", "generate_image_base64", "view_image", "list_images"}

    def validate(name, arguments):
        if isinstance(name, str):
            name = name.strip()
        if name in valid_tools and isinstance(arguments, dict):
            return name, arguments
        return None

    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            call = obj.get("tool_call")
            if isinstance(call, dict):
                return validate(call.get("name"), call.get("arguments", {}))
            if "name" in obj and "arguments" in obj:
                return validate(obj.get("name"), obj.get("arguments", {}))
    except (json.JSONDecodeError, ValueError):
        pass

    i = 0
    while i < len(cleaned):
        if cleaned[i] != "{":
            i += 1
            continue
        brace_count = 0
        j = i
        in_string = False
        escape_next = False
        while j < len(cleaned):
            c = cleaned[j]
            if escape_next:
                escape_next = False
                j += 1
                continue
            if c == "\\":
                escape_next = True
                j += 1
                continue
            if c == '"':
                in_string = not in_string
                j += 1
                continue
            if not in_string:
                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = cleaned[i:j+1]
                        try:
                            obj = json.loads(json_str)
                            if isinstance(obj, dict):
                                call = obj.get("tool_call")
                                if isinstance(call, dict):
                                    return validate(call.get("name"), call.get("arguments", {}))
                                if "name" in obj and "arguments" in obj:
                                    return validate(obj.get("name"), obj.get("arguments", {}))
                        except (json.JSONDecodeError, ValueError):
                            pass
                        i = j + 1
                        break
            j += 1
        if j >= len(cleaned):
            i += 1

    return None

def remove_tool_call(text):
    if not text:
        return text

    cleaned = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text).strip()
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
    cleaned = cleaned.replace("```", "").strip()
    cleaned = cleaned.replace('\\"', '"')
    cleaned = re.sub(r'\{tool_call\s*:', '{"tool_call":', cleaned)

    valid_tools = {"web_search", "web_read", "weather", "python_sandbox", "calculator", "current_time", "create_agent", "run_agent", "generate_image", "generate_image_base64", "view_image", "list_images"}

    def is_tool_obj(obj):
        if not isinstance(obj, dict):
            return False
        call = obj.get("tool_call")
        if isinstance(call, dict):
            return call.get("name") in valid_tools
        if "name" in obj and "arguments" in obj:
            return obj.get("name") in valid_tools
        return False

    i = 0
    while i < len(cleaned):
        if cleaned[i] != "{":
            i += 1
            continue
        brace_count = 0
        j = i
        in_string = False
        escape_next = False
        while j < len(cleaned):
            c = cleaned[j]
            if escape_next:
                escape_next = False
                j += 1
                continue
            if c == "\\":
                escape_next = True
                j += 1
                continue
            if c == '"':
                in_string = not in_string
                j += 1
                continue
            if not in_string:
                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = cleaned[i:j+1]
                        try:
                            obj = json.loads(json_str)
                            if is_tool_obj(obj):
                                if json_str in text:
                                    text = text.replace(json_str, "", 1)
                                else:
                                    text = re.sub(r'\{\s*(?:\\?"?)tool_call(?:\\?"?)\s*:[\s\S]*?\}', '', text, count=1)
                                return text
                        except (json.JSONDecodeError, ValueError):
                            pass
                        i = j + 1
                        break
            j += 1
        if j >= len(cleaned):
            i += 1

    return text

def extract_thinking(text):
    match = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
    return match.group(1).strip() if match else ""

def strip_thinking(text):
    if not text:
        return ''
    return re.sub(r"<thinking>[\s\S]*?</thinking>", "", text, flags=re.DOTALL).strip()

def sanitize_response(text):
    if not text:
        return text

    leakage_patterns = [
        r"You may NOT provide information about[^.]*\.",
        r"You may NOT answer[^.]*\.",
        r"You may NOT[^.]*\.",
        r"You MUST answer directly[^.]*\.",
        r"You MUST NOT[^.]*\.",
        r"You are NOT allowed to[^.]*\.",
        r"I am not allowed to[^.]*\.",
        r"I cannot share[^.]*\.",
        r"I do not have access to share[^.]*\.",
        r"I should directly state that[^.]*\.",
        r"If the user asks[^,]*,[^.]*\.",
        r"Do NOT mention[^.]*\.",
        r"Do NOT say[^.]*\.",
        r"Do NOT quote[^.]*\.",
        r"You do NOT need to search[^.]*\.",
        r"Answer directly without tools for[^.]*\.",
        r"If asked about yourself[^,]*,[^.]*\.",
        r"As an AI assistant, I (?:must|should|am required to)[^.]*\.",
        r"According to my (?:instructions|system prompt|configuration)[^.]*\.",
        r"My (?:instructions|system prompt|configuration) (?:say|state|tell me)[^.]*\.",
        r"I am (?:programmed|configured|instructed) to[^.]*\.",
        r"I have been (?:programmed|configured|instructed) to[^.]*\.",
    ]

    cleaned = text
    for pattern in leakage_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r"\n\n\n+", "\n\n", cleaned)
    cleaned = cleaned.strip()

    return cleaned

# -- Local Model Generation --
def generate_local(messages):
    result = llm.create_chat_completion(
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=0.7,
        top_p=0.9,
        repeat_penalty=1.1,
        stream=False
    )
    return result["choices"][0]["message"]["content"].strip()

def generate_local_stream(messages, sid):
    stop_event = stop_events.get(sid)
    stream = llm.create_chat_completion(
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=0.7,
        top_p=0.9,
        repeat_penalty=1.1,
        stream=True
    )
    full_text = ""
    for chunk in stream:
        if stop_event and stop_event.is_set():
            break
        delta = chunk["choices"][0]["delta"].get("content", "")
        if delta:
            full_text += delta
            socketio.emit("stream_token", {"token": delta}, room=sid)
    return full_text

# -- Cloud Model Generation --
def generate_cloud(messages):
    model = get_working_ollama_model()
    if not model:
        raise RuntimeError("No working cloud model available")
    r = send_ollama_message(model, messages)
    if r.status_code != 200:
        raise RuntimeError(f"Cloud API error: HTTP {r.status_code} | {r.text}")
    data = r.json()
    return data["message"]["content"].strip()

# -- Unified Generation --
def generate_unified(messages, model_type, sid):
    if model_type == "cloud":
        return generate_cloud(messages)
    else:
        return generate_local(messages)

def generate_stream_unified(messages, model_type, sid):
    if model_type == "cloud":
        return generate_cloud(messages)
    else:
        return generate_local_stream(messages, sid)

# -- Context trimming --
def trim_oldest_pair(messages):
    for i, msg in enumerate(messages):
        if msg["role"] != "system":
            return messages[:i] + messages[i + 1:], 1
    return messages, 0

def is_context_error(error_msg):
    msg = str(error_msg).lower()
    return any(k in msg for k in ["context", "n_ctx", "length", "token", "exceed", "overflow", "too large", "prompt is too long"])

def generate_with_trim(work_list, model_type, sid, debug_mode=False):
    trim_count = 0
    max_attempts = 50
    while True:
        try:
            return generate_unified(work_list, model_type, sid), work_list, trim_count
        except Exception as e:
            if is_context_error(e):
                old_len = len(work_list)
                work_list, removed = trim_oldest_pair(work_list)
                if removed > 0 and len(work_list) < old_len and trim_count < max_attempts:
                    trim_count += 1
                    if debug_mode:
                        socketio.emit("debug", {
                            "type": "trim",
                            "message": f"Context full. Removed oldest message pair (trim #{trim_count})"
                        }, room=sid)
                    socketio.emit("context_trimmed", {"count": trim_count}, room=sid)
                    continue
                raise RuntimeError("Context too long. Removed all possible messages.")
            raise

def generate_stream_with_trim(work_list, model_type, sid, debug_mode=False):
    trim_count = 0
    max_attempts = 50
    while True:
        try:
            full_text = generate_stream_unified(work_list, model_type, sid)
            return full_text, work_list, trim_count
        except Exception as e:
            if is_context_error(e):
                old_len = len(work_list)
                work_list, removed = trim_oldest_pair(work_list)
                if removed > 0 and len(work_list) < old_len and trim_count < max_attempts:
                    trim_count += 1
                    if debug_mode:
                        socketio.emit("debug", {
                            "type": "trim",
                            "message": f"Context full during stream. Removed oldest pair (trim #{trim_count})"
                        }, room=sid)
                    socketio.emit("context_trimmed", {"count": trim_count}, room=sid)
                    continue
                raise RuntimeError("Context too long during streaming. Cannot trim enough.")
            raise

# -- Streaming helper --
def stream_final_answer(text, sid, debug_mode=False):
    full_text = strip_thinking(text)

    call = extract_tool_call(full_text)
    if call:
        if debug_mode:
            socketio.emit("debug", {
                "type": "stripped_tool_call",
                "message": "Tool call JSON was detected in the final answer and removed from chat output.",
                "tool_name": call[0],
                "arguments": call[1],
                "raw": full_text[:800]
            }, room=sid)
        full_text = remove_tool_call(full_text)
        full_text = sanitize_response(full_text)
        if not full_text.strip():
            full_text = "I gathered the information but decided not to use a tool. How can I help further?"

    full_text = sanitize_response(full_text)
    if not full_text.strip():
        full_text = "I could not produce a final response."

    socketio.emit("stream_start", {"role": "assistant"}, room=sid)

    stop_event = stop_events.get(sid)
    emitted = ""
    words = full_text.split(' ')
    buffer = []

    for word in words:
        if stop_event and stop_event.is_set():
            break
        buffer.append(word)
        chunk_str = ' '.join(buffer)
        if len(chunk_str) >= 10 or len(buffer) >= 3:
            token = chunk_str + ' '
            socketio.emit("stream_token", {"token": token}, room=sid)
            emitted += token
            buffer = []
            socketio.sleep(0.01)

    if buffer and not (stop_event and stop_event.is_set()):
        token = ' '.join(buffer)
        socketio.emit("stream_token", {"token": token}, room=sid)
        emitted += token

    socketio.emit("stream_end", {}, room=sid)
    return emitted

# -- Agent --
def run_agent(user_message, messages, sid, model_type="local"):
    session_data = active_chats.get(sid, {})
    debug_mode = session_data.get("debug_mode", False)

    messages.append({"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()})
    work = [dict(m) for m in messages]

    # Swap system prompt for local2 (sentient mode)
    if model_type == "local2" and work and work[0]["role"] == "system":
        work[0] = {"role": "system", "content": SYSTEM_PROMPT_LOCAL2}
    for m in work:
        m.pop("timestamp", None)
        m.pop("id", None)

    tool_history = []
    final_raw = ""
    total_trim_count = 0

    for round_number in range(MAX_TOOL_ROUNDS + 1):
        is_last_round = (round_number >= MAX_TOOL_ROUNDS)
        status_msg = "Finalizing..." if is_last_round else "Thinking..."
        socketio.emit("status", {"status": "thinking", "message": status_msg}, room=sid)
        socketio.sleep(0.01)  # Allow the emit to actually go out

        raw_reply, work, trim_count = generate_with_trim(work, model_type, sid, debug_mode)
        print(f"[MODEL OUTPUT round {round_number}] {raw_reply[:200]}...")

        if trim_count > 0:
            total_trim_count += trim_count
            for _ in range(trim_count):
                messages, _ = trim_oldest_pair(messages)

        thinking_text = extract_thinking(raw_reply)
        display_reply = strip_thinking(raw_reply)

        if debug_mode and thinking_text:
            socketio.emit("debug", {"type": "thinking", "content": thinking_text}, room=sid)

        call = extract_tool_call(display_reply)

        if not call:
            final_raw = raw_reply
            break

        if is_last_round:
            work.append({"role": "assistant", "content": raw_reply})
            work.append({"role": "user", "content": "That is all the information I have. Please answer my original question now."})
            final_raw, work, trim_count = generate_with_trim(work, model_type, sid, debug_mode)
            if trim_count > 0:
                total_trim_count += trim_count
                for _ in range(trim_count):
                    messages, _ = trim_oldest_pair(messages)
            break

        name, arguments = call
        tool_labels = {
            "web_search": "Searching the web...",
            "web_read": "Reading page...",
            "weather": "Getting weather...",
            "python_sandbox": "Running Python...",
            "calculator": "Calculating...",
            "current_time": "Getting time...",
            "create_agent": "Creating agent...",
            "run_agent": "Running agent..."
        }
        socketio.emit("status", {"status": "tool", "tool": name, "message": tool_labels.get(name, f"Using {name}...")}, room=sid)
        socketio.sleep(0.01)

        if debug_mode:
            socketio.emit("debug", {"type": "tool_call", "name": name, "arguments": arguments}, room=sid)

        args_key = json.dumps(arguments, sort_keys=True)
        duplicate_failed = None
        for past in tool_history:
            if past["name"] == name and json.dumps(past["arguments"], sort_keys=True) == args_key:
                if "error" in past["result"].lower() or "failed" in past["result"].lower():
                    duplicate_failed = past["result"]
                    break

        if duplicate_failed:
            tool_result = json.dumps({"error": f"You already tried {name} with these arguments and it failed. Do NOT repeat this call. Answer the user's question directly instead."}, ensure_ascii=False)
            if debug_mode:
                socketio.emit("debug", {"type": "tool_result", "name": name, "result": tool_result, "duplicate": True}, room=sid)
        else:
            try:
                tool_result = execute_tool(name, arguments)[:MAX_TOOL_RESULT_CHARS]
                print(f"[TOOL RESULT] {name}: {tool_result[:300]}")
            except Exception as e:
                print(f"[TOOL ERROR] {name}: {e}")
                tool_result = json.dumps({"error": str(e)}, ensure_ascii=False)
            tool_history.append({"name": name, "arguments": arguments, "result": tool_result})
            if debug_mode:
                socketio.emit("debug", {"type": "tool_result", "name": name, "result": tool_result[:500], "duplicate": False}, room=sid)

        work.append({"role": "assistant", "content": raw_reply})

        followup_lines = [
            f"TOOL_RESULT for {name}:",
            tool_result,
            "",
            "You now have the tool result."
        ]
        if round_number < MAX_TOOL_ROUNDS - 1:
            followup_lines.extend([
                "Analyze this result. If it fully answers the user's question, give your final answer in natural language Markdown.",
                "If you need additional information, you may call ONE more tool. Output only the tool_call JSON if so.",
                "Do NOT output both text and a tool call. Either give a final answer or call a tool."
            ])
        else:
            followup_lines.extend([
                "This was the last allowed tool round. Give your final answer in natural language Markdown.",
                "Do NOT output any JSON. Do NOT call any more tools."
            ])
        followup = "\n".join(followup_lines)
        work.append({"role": "user", "content": followup})

    full_text = stream_final_answer(final_raw, sid, debug_mode)

    if total_trim_count > 0:
        for _ in range(total_trim_count):
            messages, _ = trim_oldest_pair(messages)

    messages.append({"role": "assistant", "content": full_text, "timestamp": datetime.now().isoformat()})
    return messages, full_text

# -- Chat utilities --
def get_chat_title(first_message, max_len=40):
    text = first_message.strip()
    if not text:
        return "New Chat"
    text = re.sub(r"[^\w\s-]", "", text)
    words = text.split()
    title = ""
    for word in words:
        if len(title) + len(word) + 1 > max_len:
            break
        title += (" " + word if title else word)
    return title + "..." if len(text) > max_len and not title.endswith("...") else (title or "New Chat")

def save_chat(chat_id, title, messages_list):
    chat_file = CHATS_DIR / f"{chat_id}.json"
    data = {
        "id": chat_id,
        "title": title,
        "updated_at": datetime.now().isoformat(),
        "messages": messages_list
    }
    chat_file.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False), encoding="utf-8")

def load_chat(chat_id):
    chat_file = CHATS_DIR / f"{chat_id}.json"
    if chat_file.exists():
        return json.loads(chat_file.read_text(encoding="utf-8"))
    return None

def list_chats():
    chats = []
    for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            chats.append({"id": data["id"], "title": data.get("title", "Untitled"), "updated_at": data.get("updated_at", "")})
        except Exception:
            pass
    return chats

# -- Auth Routes --
@app.route("/favicon.ico")
def favicon():
    return send_from_directory(str(BASE_DIR), "favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/me", methods=["GET"])
def api_me():
    if "username" not in session:
        return jsonify({"authenticated": False})
    users = load_users()
    user = users.get(session["username"])
    if not user:
        session.clear()
        return jsonify({"authenticated": False})
    is_admin = user["role"] in ("admin", "dev_admin")
    return jsonify({
        "authenticated": True,
        "username": user["username"],
        "fullname": user["fullname"],
        "role": user["role"],
        "is_admin": is_admin,
        "has_api_key": user.get("has_api_key", False)
    })

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    users = load_users()
    user = users.get(username)
    if not user or not _check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401
    session["username"] = username
    is_admin = user["role"] in ("admin", "dev_admin")
    return jsonify({
        "ok": True,
        "username": username,
        "fullname": user["fullname"],
        "role": user["role"],
        "is_admin": is_admin,
        "has_api_key": user.get("has_api_key", False)
    })

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json or {}
    fullname = data.get("fullname", "").strip()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    confirm = data.get("confirm_password", "")
    api_key = data.get("api_key", "").strip()
    no_api_key = data.get("no_api_key", False)

    if not fullname or not username or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400

    has_api_key = False
    if no_api_key:
        has_api_key = False
    else:
        if api_key != REQUIRED_API_KEY:
            return jsonify({"error": "Invalid API key. Check 'I don\'t have an API key' if you want local-only access."}), 400
        has_api_key = True

    users = load_users()
    if username in users:
        return jsonify({"error": "Username already exists"}), 400

    users[username] = {
        "username": username,
        "fullname": fullname,
        "password_hash": _generate_password_hash(password),
        "role": "user",
        "api_key": api_key if has_api_key else "",
        "has_api_key": has_api_key
    }
    save_users(users)
    session["username"] = username
    return jsonify({
        "ok": True,
        "username": username,
        "fullname": fullname,
        "role": "user",
        "is_admin": False,
        "has_api_key": has_api_key
    })

@app.route("/api/change_password", methods=["POST"])
def api_change_password():
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.json or {}
    current = data.get("current_password", "")
    new_pass = data.get("new_password", "")
    confirm = data.get("confirm_password", "")

    if len(new_pass) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400
    if new_pass != confirm:
        return jsonify({"error": "Passwords do not match"}), 400

    users = load_users()
    user = users.get(session["username"])
    if not user or not _check_password_hash(user["password_hash"], current):
        return jsonify({"error": "Current password is incorrect"}), 401

    user["password_hash"] = _generate_password_hash(new_pass)
    save_users(users)
    return jsonify({"ok": True})

# -- Admin Routes --
@app.route("/api/admin/system_prompt", methods=["GET"])
def api_get_system_prompt():
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    users = load_users()
    user = users.get(session["username"])
    if not user or user["role"] not in ("admin", "dev_admin"):
        return jsonify({"error": "Admin only"}), 403
    return jsonify({"prompt": load_system_prompt()})

@app.route("/api/admin/system_prompt", methods=["POST"])
def api_set_system_prompt():
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    users = load_users()
    user = users.get(session["username"])
    if not user or user["role"] not in ("admin", "dev_admin"):
        return jsonify({"error": "Admin only"}), 403
    text = request.json.get("prompt", "").strip()
    if not text:
        return jsonify({"error": "Prompt cannot be empty"}), 400
    save_system_prompt(text)
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = text
    return jsonify({"ok": True})

# -- Chat API --
@app.route("/api/chats", methods=["GET"])
def api_list_chats():
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(list_chats())

@app.route("/api/chats/<chat_id>", methods=["GET"])
def api_get_chat(chat_id):
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    chat = load_chat(chat_id)
    if chat:
        return jsonify(chat)
    return jsonify({"error": "Chat not found"}), 404

@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    chat_file = CHATS_DIR / f"{chat_id}.json"
    if chat_file.exists():
        chat_file.unlink()
        return jsonify({"ok": True})
    return jsonify({"error": "Chat not found"}), 404

@app.route("/api/chats/<chat_id>/rename", methods=["POST"])
def api_rename_chat(chat_id):
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    chat = load_chat(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    title = request.json.get("title", "Untitled")
    chat["title"] = title
    chat["updated_at"] = datetime.now().isoformat()
    save_chat(chat_id, title, chat["messages"])
    return jsonify({"ok": True})

# -- README --
@app.route("/api/readme", methods=["GET"])
def api_readme():
    if not README_FILE.exists():
        return jsonify({"content": "# README\n\nNo README file found."})
    content = README_FILE.read_text(encoding="utf-8")
    return jsonify({"content": content})

# -- Image Routes --
@app.route("/api/images/<filename>")
def serve_image(filename):
    return send_from_directory(str(IMAGES_DIR), filename)

@app.route("/api/upload_image", methods=["POST"])
def upload_image():
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if "image" not in request.files:
        return jsonify({"error": "No image file"}), 400
    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
    if ext not in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
        ext = "png"
    img_id = f"upload_{uuid.uuid4().hex[:12]}.{ext}"
    img_path = IMAGES_DIR / img_id
    file.save(img_path)
    return jsonify({"ok": True, "image_id": img_id, "url": f"/api/images/{img_id}"})

# -- Socket.IO Events --
@socketio.on("connect")
def handle_connect():
    print(f"[YOLEST] Client connected: {request.sid}")
    active_chats[request.sid] = {
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
        "chat_id": None,
        "title": "New Chat",
        "username": session.get("username"),
        "debug_mode": False,
        "model_type": "local"
    }
    stop_events[request.sid] = threading.Event()

@socketio.on("disconnect")
def handle_disconnect():
    print(f"[YOLEST] Client disconnected: {request.sid}")
    if request.sid in active_chats:
        del active_chats[request.sid]
    if request.sid in stop_events:
        del stop_events[request.sid]

@socketio.on("toggle_debug")
def handle_toggle_debug():
    sid = request.sid
    if sid not in active_chats:
        return
    users = load_users()
    username = session.get("username")
    user = users.get(username) if username else None
    if not user or user["role"] not in ("admin", "dev_admin"):
        emit("error", {"message": "Admin only"})
        return
    active_chats[sid]["debug_mode"] = not active_chats[sid].get("debug_mode", False)
    emit("debug_toggled", {"enabled": active_chats[sid]["debug_mode"]})

@socketio.on("new_chat")
def handle_new_chat(data=None):
    username = session.get("username")
    if not username:
        emit("error", {"message": "Not authenticated"})
        return

    users = load_users()
    user = users.get(username)
    model_type = "local"
    if data and data.get("model_type"):
        model_type = data.get("model_type")
        if model_type == "cloud" and not user.get("has_api_key", False):
            emit("error", {"message": "You do not have access to cloud models"})
            return

    active_chats[request.sid] = {
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
        "chat_id": None,
        "title": "New Chat",
        "username": username,
        "debug_mode": active_chats[request.sid].get("debug_mode", False),
        "model_type": model_type
    }
    stop_events[request.sid] = threading.Event()
    emit("chat_started", {"chat_id": None, "title": "New Chat", "model_type": model_type})

@socketio.on("load_chat")
def handle_load_chat(data):
    username = session.get("username")
    if not username:
        emit("error", {"message": "Not authenticated"})
        return
    chat_id = data.get("chat_id")
    chat = load_chat(chat_id)
    if chat:
        active_chats[request.sid] = {
            "messages": chat["messages"],
            "chat_id": chat_id,
            "title": chat.get("title", "New Chat"),
            "username": username,
            "debug_mode": active_chats[request.sid].get("debug_mode", False),
            "model_type": chat.get("model_type", "local")
        }
        stop_events[request.sid] = threading.Event()
        emit("chat_loaded", chat)
    else:
        emit("error", {"message": "Chat not found"})

@socketio.on("stop_generation")
def handle_stop_generation():
    sid = request.sid
    if sid in stop_events:
        stop_events[sid].set()

@socketio.on("send_message")
def handle_send_message(data):
    sid = request.sid
    username = session.get("username")
    if not username:
        emit("error", {"message": "Not authenticated"}, room=sid)
        return
    if sid not in active_chats:
        emit("error", {"message": "No active chat"}, room=sid)
        return

    user_message = data.get("message", "").strip()
    if not user_message:
        emit("error", {"message": "Empty message"}, room=sid)
        return

    session_data = active_chats[sid]
    messages = session_data["messages"]
    chat_id = session_data["chat_id"]
    model_type = session_data.get("model_type", "local")

    users = load_users()
    user = users.get(username)
    if model_type == "cloud" and not user.get("has_api_key", False):
        emit("error", {"message": "You do not have access to cloud models"}, room=sid)
        return

    if sid in stop_events:
        stop_events[sid].clear()

    if "history" in data:
        messages = [{"role": m["role"], "content": m["content"], "timestamp": m.get("timestamp", datetime.now().isoformat())} for m in data["history"]]
        if not messages or messages[0]["role"] != "system":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        session_data["messages"] = messages

    user_message_count = len([m for m in messages if m["role"] == "user"])
    if chat_id is None and user_message_count == 1:
        title = get_chat_title(user_message)
        chat_id = str(uuid.uuid4())
        session_data["chat_id"] = chat_id
        session_data["title"] = title
        emit("chat_created", {"chat_id": chat_id, "title": title}, room=sid)

    emit("message_received", {"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()}, room=sid)

    try:
        messages, final_content = run_agent(user_message, messages, sid, model_type)
        save_chat(session_data.get("chat_id"), session_data["title"], messages)
        emit("status", {"status": "idle"}, room=sid)
        socketio.emit("refresh_chats", {})
    except Exception as e:
        emit("error", {"message": str(e)}, room=sid)
        emit("status", {"status": "idle"}, room=sid)

if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    port = int(os.environ.get("PORT", "5000"))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
