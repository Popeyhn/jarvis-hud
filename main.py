import os
import sys
import json
import datetime
import re
import random
import threading
import time
import base64
import hashlib
from urllib.parse import quote_plus
from flask import Flask, render_template, request, jsonify

# ----------------- CONFIG & PATHS -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "jarvis_config.json")
HISTORY_FILE = os.path.join(BASE_DIR, "jarvis_memory.json")
ROUTINES_FILE = os.path.join(BASE_DIR, "jarvis_routines.json")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

try:
    import requests
except ImportError:
    requests = None

DEFAULT_CONFIG = {
    "gemini_api_keys": [],          # Supports multiple keys with auto-rotation
    "active_key_index": 0,
    "gemini_model": "gemini-2.5-flash",
    "brain_mode": "hybrid",
    "voice_enabled": True,
    "auto_search": True,
    "max_history_turns": 15
}

# Android Package Mappings for "Open App" tool
APP_PACKAGES = {
    "youtube": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
    "chrome": "com.android.chrome",
    "browser": "com.android.chrome",
    "camera": "com.google.android.GoogleCamera",
    "settings": "com.android.settings",
    "maps": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm",
    "spotify": "com.spotify.music",
    "telegram": "org.telegram.messenger",
    "gallery": "com.google.android.apps.photos",
    "calculator": "com.google.android.calculator",
    "clock": "com.google.android.deskclock"
}

# ----------------- CRYPTOGRAPHY TOOLKIT -----------------
class CryptoEngine:
    @staticmethod
    def sha256_hash(text):
        return hashlib.sha256(text.encode()).hexdigest()

    @staticmethod
    def md5_hash(text):
        return hashlib.md5(text.encode()).hexdigest()

    @staticmethod
    def b64_encode(text):
        return base64.b64encode(text.encode()).decode()

    @staticmethod
    def b64_decode(text):
        try:
            return base64.b64decode(text.encode()).decode()
        except Exception:
            return "Error: Invalid Base64 payload."

    @staticmethod
    def xor_cipher(text, key):
        if not key:
            key = "JARVIS_STEALTH_DEFAULT_KEY"
        key_bytes = key.encode()
        text_bytes = text.encode()
        xored = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text_bytes)])
        return base64.b64encode(xored).decode()

    @staticmethod
    def xor_decipher(encoded_b64, key):
        if not key:
            key = "JARVIS_STEALTH_DEFAULT_KEY"
        try:
            raw = base64.b64decode(encoded_b64.encode())
            key_bytes = key.encode()
            dec = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw)])
            return dec.decode()
        except Exception as e:
            return f"Decryption failed: {e}"


# ----------------- JARVIS CORE -----------------
class JarvisCore:
    def __init__(self):
        self.config = self.load_config()
        self.history = self.load_history()
        self.routines = self.load_routines()

    def load_config(self):
        data = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    data.update(saved)
            except Exception:
                pass
        return data

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_routines(self):
        if os.path.exists(ROUTINES_FILE):
            try:
                with open(ROUTINES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "morning briefing": ["status", "search world news today", "search weather today"],
            "security audit": ["status", "crypto hash check"]
        }

    def save_routines(self):
        try:
            with open(ROUTINES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.routines, f, indent=2)
        except Exception:
            pass

    def add_history(self, role, content):
        self.history.append({
            "role": role,
            "content": str(content),
            "timestamp": datetime.datetime.now().isoformat()
        })
        max_items = max(10, int(self.config.get("max_history_turns", 15)) * 2)
        self.history = self.history[-max_items:]
        self.save_history()

    def get_active_api_key(self):
        keys = self.config.get("gemini_api_keys", [])
        if not keys:
            return ""
        idx = self.config.get("active_key_index", 0) % len(keys)
        return keys[idx]

    def rotate_key(self):
        keys = self.config.get("gemini_api_keys", [])
        if len(keys) > 1:
            idx = (self.config.get("active_key_index", 0) + 1) % len(keys)
            self.config["active_key_index"] = idx
            self.save_config()
            return f"Rotated to Key Pool slot #{idx + 1}."
        return "Single key pool active."

    def web_search(self, query, max_results=4):
        if requests is None:
            return None, "Requests module missing."
        try:
            url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
            headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) Chrome/122.0 Mobile"}
            res = requests.get(url, headers=headers, timeout=12)
            res.raise_for_status()

            links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', res.text, flags=re.I | re.S)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)>', res.text, flags=re.I | re.S)

            results = []
            for i, (link, title_html) in enumerate(links[:max_results]):
                title = re.sub(r"<.*?>|\s+", " ", title_html).strip()
                snippet = re.sub(r"<.*?>|\s+", " ", snippets[i]).strip() if i < len(snippets) else ""
                results.append({"title": title, "url": link, "snippet": snippet})

            if not results:
                return [], "No results found."
            return results, None
        except Exception as e:
            return None, f"Search failed: {e}"

    def format_search_results(self, results):
        if not results:
            return ""
        return "\n\n".join([f"[{i+1}] {item['title']}\nURL: {item['url']}\nSummary: {item['snippet']}" for i, item in enumerate(results)])

    def call_gemini(self, user_input, web_context="", file_context=""):
        keys = self.config.get("gemini_api_keys", [])
        if not keys:
            return None, "No API key found. Open SETTINGS to add your Gemini API key(s)."

        model = self.config.get("gemini_model", "gemini-2.5-flash")
        recent = self.history[-max(2, int(self.config.get("max_history_turns", 15)) * 2):]

        contents = []
        for msg in recent:
            if msg["role"] in ("user", "assistant"):
                contents.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [{"text": msg["content"]}]
                })

        prompt = (
            "You are JARVIS, an ultra-advanced AI tactical assistant. "
            "Prioritize concise, direct, intelligent vocal-ready responses. "
            "When analyzing data, files, or cryptography, deliver clean operational breakdowns.\n\n"
            f"USER DIRECTIVE: {user_input}"
        )
        if file_context:
            prompt += f"\n\n[ATTACHED FILE CONTEXT]:\n{file_context}"
        if web_context:
            prompt += f"\n\n[LIVE SEARCH TELEMETRY]:\n{web_context}"

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        # Multi-key failover attempt
        for _ in range(len(keys)):
            current_key = self.get_active_api_key()
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                res = requests.post(
                    url,
                    headers={"x-goog-api-key": current_key, "Content-Type": "application/json"},
                    json={"contents": contents, "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1200}},
                    timeout=30
                )
                if res.status_code in (429, 403):
                    # Rotate key and retry
                    self.rotate_key()
                    continue
                res.raise_for_status()
                data = res.json()
                parts = data.get("candidates", [])[0].get("content", {}).get("parts", [])
                text = "".join(part.get("text", "") for part in parts).strip()
                if text:
                    return text, None
            except Exception as e:
                self.rotate_key()

        return None, "All Cloud API keys exhausted or unreachable. Switched to offline core."

    def launch_android_app(self, app_name):
        app_name_clean = app_name.lower().replace("open ", "").replace("launch ", "").strip()
        pkg = APP_PACKAGES.get(app_name_clean, app_name_clean)

        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            currentActivity = PythonActivity.mActivity
            pm = currentActivity.getPackageManager()
            intent = pm.getLaunchIntentForPackage(pkg)
            if intent:
                currentActivity.startActivity(intent)
                return f"Launching {app_name_clean.upper()} [{pkg}]..."
            else:
                return f"App '{app_name_clean}' not found on this device."
        except Exception:
            return f"Direct launch triggered for '{app_name_clean}'. (Package: {pkg})"

    def handle_crypto(self, text):
        t = text.strip()
        if t.startswith("hash sha256 "):
            return f"SHA-256 HASH:\n{CryptoEngine.sha256_hash(t[12:].strip())}"
        if t.startswith("hash md5 "):
            return f"MD5 HASH:\n{CryptoEngine.md5_hash(t[9:].strip())}"
        if t.startswith("encrypt b64 "):
            return f"BASE64 ENCODED:\n{CryptoEngine.b64_encode(t[12:].strip())}"
        if t.startswith("decrypt b64 "):
            return f"BASE64 DECODED:\n{CryptoEngine.b64_decode(t[12:].strip())}"
        if t.startswith("encrypt xor "):
            parts = t[12:].split(" key ")
            val = parts[0].strip()
            k = parts[1].strip() if len(parts) > 1 else ""
            return f"XOR-ENCRYPTED (B64):\n{CryptoEngine.xor_cipher(val, k)}"
        if t.startswith("decrypt xor "):
            parts = t[12:].split(" key ")
            val = parts[0].strip()
            k = parts[1].strip() if len(parts) > 1 else ""
            return f"XOR-DECRYPTED:\n{CryptoEngine.xor_decipher(val, k)}"
        return None

    def execute_routine(self, routine_name):
        routine_name = routine_name.lower().strip()
        steps = self.routines.get(routine_name)
        if not steps:
            return f"Routine '{routine_name}' is not registered."
        
        results = [f"--- EXECUTING MACRO: {routine_name.upper()} ---"]
        for step in steps:
            reply = self.ask(step)
            results.append(f"▶ [{step}]: {reply.get('response', '')}")
        return "\n\n".join(results)

    def offline_reply(self, text):
        t = text.lower()
        if any(w in t for w in ["hi", "hello", "hey", "jarvis"]):
            return "JARVIS online. Tactical systems, voice synth, and neural cores fully operational."
        if "time" in t:
            return f"Current time: {datetime.datetime.now().strftime('%H:%M:%S')}."
        if "date" in t:
            return f"Today is {datetime.date.today().strftime('%A, %d %B %Y')}."
        return "Core offline mode active. Add an API key in SETTINGS for continuous cloud intelligence."

    def ask(self, text, file_context=""):
        cmd_clean = text.strip()
        lower = cmd_clean.lower()

        # 1. Native App Opener
        if lower.startswith("open ") or lower.startswith("launch "):
            app_resp = self.launch_android_app(lower)
            return {"response": app_resp, "source": "SYSTEM_TOOL"}

        # 2. Cryptography Engine
        crypto_res = self.handle_crypto(cmd_clean)
        if crypto_res:
            return {"response": crypto_res, "source": "CRYPTO_CORE"}

        # 3. Macro / Task Automation Routine
        if lower.startswith("routine ") or lower.startswith("run macro "):
            name = lower.replace("routine ", "").replace("run macro ", "").strip()
            macro_out = self.execute_routine(name)
            return {"response": macro_out, "source": "AUTOMATION_ENGINE"}

        # 4. Web Search
        force_search = lower.startswith("search ") or lower.startswith("intel ")
        query = cmd_clean[7:].strip() if force_search else cmd_clean
        web_context = ""

        if force_search or any(k in query.lower() for k in ["latest", "news", "price", "who is", "weather", "crypto market"]):
            results, _ = self.web_search(query)
            if results:
                web_context = self.format_search_results(results)

        # 5. Cloud Brain (Gemini Multi-Key)
        answer, err = self.call_gemini(query, web_context, file_context)
        if answer:
            self.add_history("user", query)
            self.add_history("assistant", answer)
            return {"response": answer, "source": "GEMINI_CLOUD"}

        # 6. Basic Fallback
        fallback = self.offline_reply(query)
        self.add_history("user", query)
        self.add_history("assistant", fallback)
        return {"response": fallback, "source": "OFFLINE_CORE", "warning": err}


jarvis = JarvisCore()

# ----------------- FLASK REST API -----------------
app = Flask(__name__, template_folder="templates")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/query", methods=["POST"])
def handle_query():
    data = request.json or {}
    user_input = data.get("command", "").strip()
    file_context = data.get("file_context", "").strip()

    if not user_input and not file_context:
        return jsonify({"response": "No directive received.", "source": "SYSTEM"})

    res = jarvis.ask(user_input, file_context)
    return jsonify(res)

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file attached."})
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "Filename empty."})

    try:
        filename = file.filename
        filepath = os.path.join(UPLOAD_DIR, filename)
        file.save(filepath)

        # Read text or snippet
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(15000)  # Max 15KB preview
        except Exception:
            content = f"[Binary / Data file: {filename} uploaded]"

        return jsonify({
            "success": True,
            "filename": filename,
            "content": content,
            "message": f"File '{filename}' loaded into memory."
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Upload error: {e}"})

@app.route("/api/keys", methods=["GET", "POST", "DELETE"])
def handle_keys():
    if request.method == "GET":
        keys = jarvis.config.get("gemini_api_keys", [])
        masked = [k[:6] + "..." + k[-4:] if len(k) > 10 else "***" for k in keys]
        return jsonify({
            "keys": masked,
            "total": len(keys),
            "active_index": jarvis.config.get("active_key_index", 0)
        })

    if request.method == "POST":
        data = request.json or {}
        new_key = data.get("key", "").strip()
        if new_key:
            if "gemini_api_keys" not in jarvis.config:
                jarvis.config["gemini_api_keys"] = []
            if new_key not in jarvis.config["gemini_api_keys"]:
                jarvis.config["gemini_api_keys"].append(new_key)
                jarvis.save_config()
                return jsonify({"success": True, "message": "Key added to pool."})
            return jsonify({"success": True, "message": "Key already exists in pool."})
        return jsonify({"success": False, "message": "Key string is empty."})

    if request.method == "DELETE":
        jarvis.config["gemini_api_keys"] = []
        jarvis.config["active_key_index"] = 0
        jarvis.save_config()
        return jsonify({"success": True, "message": "All API keys removed."})

@app.route("/api/status", methods=["GET"])
def get_status():
    keys = jarvis.config.get("gemini_api_keys", [])
    return jsonify({
        "cloud_ready": len(keys) > 0,
        "key_count": len(keys),
        "active_key_slot": (jarvis.config.get("active_key_index", 0) % len(keys) + 1) if keys else 0,
        "model": jarvis.config.get("gemini_model", "gemini-2.5-flash"),
        "history_count": len(jarvis.history),
        "routines": list(jarvis.routines.keys())
    })

def run_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

def start_app():
    srv_thread = threading.Thread(target=run_flask, daemon=True)
    srv_thread.start()
    time.sleep(1)

    try:
        from kivy.app import App
        from kivy.uix.widget import Widget
        from jnius import autoclass

        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        WebView = autoclass('android.webkit.WebView')
        WebViewClient = autoclass('android.webkit.WebViewClient')
        LayoutParams = autoclass('android.view.ViewGroup$LayoutParams')

        class WebViewApp(App):
            def build(self):
                activity = PythonActivity.mActivity
                webview = WebView(activity)
                webview.getSettings().setJavaScriptEnabled(True)
                webview.getSettings().setDomStorageEnabled(True)
                webview.getSettings().setAllowFileAccess(True)
                webview.setWebViewClient(WebViewClient())
                webview.loadUrl("http://127.0.0.1:5000")
                activity.setContentView(webview, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
                return Widget()

        WebViewApp().run()
    except Exception:
        import webbrowser
        webbrowser.open("http://127.0.0.1:5000")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    start_app()                pass
        return []

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add_history(self, role, content):
        self.history.append({
            "role": role,
            "content": str(content),
            "timestamp": datetime.datetime.now().isoformat()
        })
        max_items = max(10, int(self.config.get("max_history_turns", 12)) * 2)
        self.history = self.history[-max_items:]
        self.save_history()

    def web_search(self, query, max_results=4):
        if requests is None:
            return None, "Requests package is not installed."
        try:
            url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
            headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) Chrome/120 Mobile Safari/537.36"}
            res = requests.get(url, headers=headers, timeout=12)
            res.raise_for_status()

            links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', res.text, flags=re.I | re.S)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)>', res.text, flags=re.I | re.S)

            results = []
            for i, (link, title_html) in enumerate(links[:max_results]):
                title = re.sub(r"<.*?>|\s+", " ", title_html).strip()
                snippet = re.sub(r"<.*?>|\s+", " ", snippets[i]).strip() if i < len(snippets) else ""
                results.append({"title": title, "url": link, "snippet": snippet})

            if not results:
                return [], "No results found."
            return results, None
        except Exception as e:
            return None, f"Search failed: {e}"

    def format_search_results(self, results):
        if not results:
            return ""
        return "\n\n".join([f"[{i+1}] {item['title']}\nURL: {item['url']}\nSummary: {item['snippet']}" for i, item in enumerate(results)])

    def call_gemini(self, user_input, web_context=""):
        api_key = self.config.get("gemini_api_key", "").strip()
        if not api_key or requests is None:
            return None, "Cloud API Key not configured."

        model = self.config.get("gemini_model", "gemini-2.5-flash")
        recent = self.history[-max(2, int(self.config.get("max_history_turns", 12)) * 2):]

        contents = []
        for msg in recent:
            if msg["role"] in ("user", "assistant"):
                contents.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [{"text": msg["content"]}]
                })

        prompt = (
            "You are JARVIS, an advanced personal AI assistant. "
            "Be accurate, concise, and futuristic. Summarize untrusted web results if present.\n\n"
            f"USER DIRECTIVE: {user_input}"
        )
        if web_context:
            prompt += f"\n\nLIVE SEARCH RESULTS:\n{web_context}"

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            res = requests.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={"contents": contents, "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}},
                timeout=30
            )
            res.raise_for_status()
            data = res.json()
            parts = data.get("candidates", [])[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts).strip()
            return (text, None) if text else (None, "Empty response.")
        except Exception as e:
            return None, f"Gemini Error: {e}"

    def offline_reply(self, text):
        t = text.lower()
        if any(w in t for w in ["hi", "hello", "hey"]):
            return "Greetings, Boss. Systems standing by."
        if "time" in t:
            return f"Current time is {datetime.datetime.now().strftime('%H:%M:%S')}."
        if "date" in t:
            return f"Today is {datetime.date.today().strftime('%A, %d %B %Y')}."
        return "Core offline fallback operational. Enter Gemini API key in settings for full intelligence."

    def ask(self, text):
        force_search = text.lower().startswith("search ")
        query = text[7:].strip() if force_search else text
        web_context = ""

        if force_search or any(k in query.lower() for k in ["latest", "news", "price", "who is", "weather"]):
            results, _ = self.web_search(query)
            if results:
                web_context = self.format_search_results(results)

        # 1. Cloud First
        answer, err = self.call_gemini(query, web_context)
        if answer:
            self.add_history("user", query)
            self.add_history("assistant", answer)
            return {"response": answer, "source": "CLOUD_AI"}

        # 2. Offline Fallback
        fallback = self.offline_reply(query)
        self.add_history("user", query)
        self.add_history("assistant", fallback)
        return {"response": fallback, "source": "OFFLINE_CORE", "warning": err}

jarvis = JarvisCore()

# ----------------- FLASK APP -----------------
app = Flask(__name__, template_folder="templates")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/query", methods=["POST"])
def handle_query():
    data = request.json or {}
    user_input = data.get("command", "").strip()
    if not user_input:
        return jsonify({"response": "No command received.", "source": "SYSTEM"})
    
    # Internal Config commands
    if user_input.lower().startswith("set key "):
        key = user_input[8:].strip()
        jarvis.config["gemini_api_key"] = key
        jarvis.save_config()
        return jsonify({"response": "Gemini API key successfully saved to persistent memory.", "source": "CONFIG"})

    res = jarvis.ask(user_input)
    return jsonify(res)

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({
        "cloud_ready": bool(jarvis.config.get("gemini_api_key")),
        "model": jarvis.config.get("gemini_model", "gemini-2.5-flash"),
        "history_count": len(jarvis.history)
    })

def run_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

# ----------------- ANDROID WEBVIEW LAUNCHER -----------------
def start_app():
    # Start web server in background
    srv_thread = threading.Thread(target=run_flask, daemon=True)
    srv_thread.start()
    time.sleep(1)

    # Launch native Android WebView if running inside Android APK
    try:
        from kivy.app import App
        from kivy.uix.widget import Widget
        from jnius import autoclass

        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        WebView = autoclass('android.webkit.WebView')
        WebViewClient = autoclass('android.webkit.WebViewClient')
        LayoutParams = autoclass('android.view.ViewGroup$LayoutParams')

        class WebViewApp(App):
            def build(self):
                activity = PythonActivity.mActivity
                webview = WebView(activity)
                webview.getSettings().setJavaScriptEnabled(True)
                webview.getSettings().setDomStorageEnabled(True)
                webview.setWebViewClient(WebViewClient())
                webview.loadUrl("http://127.0.0.1:5000")
                activity.setContentView(webview, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
                return Widget()

        WebViewApp().run()
    except Exception:
        # Fallback for desktop testing / browser view
        import webbrowser
        webbrowser.open("http://127.0.0.1:5000")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    start_app()
