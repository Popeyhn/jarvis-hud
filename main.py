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

# Multi-Brain Catalog
SUPPORTED_BRAINS = {
    "gemini": {
        "name": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "description": "Google flagship multimodal AI",
        "auth_type": "header_or_query"
    },
    "groq": {
        "name": "Groq (Ultra-Fast Llama 3)",
        "default_model": "llama-3.3-70b-versatile",
        "description": "Near-instant response speed for voice",
        "auth_type": "bearer"
    },
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "default_model": "gpt-4o-mini",
        "description": "Standard OpenAI GPT models",
        "auth_type": "bearer"
    },
    "openrouter": {
        "name": "OpenRouter",
        "default_model": "deepseek/deepseek-chat",
        "description": "Universal gateway for 100+ AI models",
        "auth_type": "bearer"
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "description": "Advanced reasoning & coding",
        "auth_type": "anthropic"
    }
}

DEFAULT_CONFIG = {
    "active_brain": "gemini",
    "brain_keys": {
        "gemini": [],
        "groq": [],
        "openai": [],
        "openrouter": [],
        "claude": []
    },
    "brain_models": {
        "gemini": "gemini-2.5-flash",
        "groq": "llama-3.3-70b-versatile",
        "openai": "gpt-4o-mini",
        "openrouter": "deepseek/deepseek-chat",
        "claude": "claude-3-5-sonnet-20241022"
    },
    "auto_search": True,
    "max_history_turns": 15
}

APP_PACKAGES = {
    "youtube": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
    "chrome": "com.android.chrome",
    "camera": "com.google.android.GoogleCamera",
    "settings": "com.android.settings",
    "maps": "com.google.android.apps.maps",
    "spotify": "com.spotify.music",
    "telegram": "org.telegram.messenger",
    "calculator": "com.google.android.calculator"
}

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
            "morning briefing": ["status", "search top news today"],
            "security audit": ["status", "hash sha256 SECURE_SYSTEM_ACTIVE"]
        }

    def add_history(self, role, content):
        self.history.append({"role": role, "content": str(content), "timestamp": datetime.datetime.now().isoformat()})
        self.history = self.history[-(self.config.get("max_history_turns", 15) * 2):]
        self.save_history()

    def get_active_brain_key(self, brain):
        keys = self.config.get("brain_keys", {}).get(brain, [])
        return keys[0] if keys else ""

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
            return results or [], None
        except Exception as e:
            return None, f"Search failed: {e}"

    def call_brain_api(self, prompt_text):
        brain = self.config.get("active_brain", "gemini")
        key = self.get_active_brain_key(brain)
        model = self.config.get("brain_models", {}).get(brain, "")

        if not key:
            return None, f"No API key saved for {SUPPORTED_BRAINS.get(brain, {}).get('name', brain)}. Go to SETTINGS to configure it."

        headers = {"Content-Type": "application/json"}

        # 1. Google Gemini
        if brain == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000}
            }
            res = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=payload, timeout=25)
            res.raise_for_status()
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip(), None

        # 2. OpenAI / Groq / OpenRouter (Standard OpenAI API format)
        if brain in ("groq", "openai", "openrouter"):
            endpoints = {
                "groq": "https://api.groq.com/openai/v1/chat/completions",
                "openai": "https://api.openai.com/v1/chat/completions",
                "openrouter": "https://openrouter.ai/api/v1/chat/completions"
            }
            headers["Authorization"] = f"Bearer {key}"
            payload = {
                "model": model,
                "messages": [{"role": "system", "content": "You are JARVIS. Concise, highly intelligent voice assistant."}, {"role": "user", "content": prompt_text}],
                "temperature": 0.7
            }
            res = requests.post(endpoints[brain], headers=headers, json=payload, timeout=25)
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"].strip(), None

        # 3. Anthropic Claude
        if brain == "claude":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
            payload = {"model": model, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt_text}]}
            res = requests.post(url, headers=headers, json=payload, timeout=25)
            res.raise_for_status()
            return res.json()["content"][0]["text"].strip(), None

        return None, "Brain type not supported."

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
                return f"Launching {app_name_clean.upper()}..."
            return f"App '{app_name_clean}' not found on device."
        except Exception:
            return f"Launch directive triggered for '{app_name_clean}' [{pkg}]."

    def ask(self, text, file_context=""):
        cmd_clean = text.strip()
        lower = cmd_clean.lower()

        # Tools: App Opener
        if lower.startswith("open ") or lower.startswith("launch "):
            return {"response": self.launch_android_app(lower), "source": "APP_LAUNCHER"}

        # Tools: Cryptography
        if lower.startswith("hash sha256 "):
            return {"response": f"SHA-256:\n{hashlib.sha256(cmd_clean[12:].encode()).hexdigest()}", "source": "CRYPTO"}
        if lower.startswith("encrypt b64 "):
            return {"response": f"BASE64:\n{base64.b64encode(cmd_clean[12:].encode()).decode()}", "source": "CRYPTO"}

        # Web Search Context
        web_context = ""
        if lower.startswith("search ") or any(k in lower for k in ["news", "price", "who is", "weather"]):
            query = cmd_clean[7:].strip() if lower.startswith("search ") else cmd_clean
            results, _ = self.web_search(query)
            if results:
                web_context = "\n".join([f"- {r['title']}: {r['snippet']}" for r in results])

        prompt = f"User Directive: {cmd_clean}"
        if file_context:
            prompt += f"\n\nAttached Data:\n{file_context}"
        if web_context:
            prompt += f"\n\nLive Search Telemetry:\n{web_context}"

        try:
            answer, err = self.call_brain_api(prompt)
            if answer:
                self.add_history("user", cmd_clean)
                self.add_history("assistant", answer)
                return {"response": answer, "source": self.config.get("active_brain", "AI").upper()}
            return {"response": err or "Brain offline.", "source": "SYSTEM"}
        except Exception as e:
            return {"response": f"Connection Error: {e}", "source": "SYSTEM"}

jarvis = JarvisCore()

# ----------------- REST API -----------------
app = Flask(__name__, template_folder="templates")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/query", methods=["POST"])
def query():
    data = request.json or {}
    return jsonify(jarvis.ask(data.get("command", ""), data.get("file_context", "")))

@app.route("/api/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"success": False, "message": "No file."})
    filepath = os.path.join(UPLOAD_DIR, file.filename)
    file.save(filepath)
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(15000)
    except Exception:
        content = f"[File {file.filename} loaded]"
    return jsonify({"success": True, "filename": file.filename, "content": content})

@app.route("/api/brains", methods=["GET", "POST"])
def brains():
    if request.method == "GET":
        return jsonify({
            "active_brain": jarvis.config.get("active_brain", "gemini"),
            "catalog": SUPPORTED_BRAINS,
            "configured_keys": {k: (len(v) > 0) for k, v in jarvis.config.get("brain_keys", {}).items()},
            "models": jarvis.config.get("brain_models", {})
        })
    if request.method == "POST":
        data = request.json or {}
        brain = data.get("brain")
        key = data.get("key", "").strip()
        model = data.get("model", "").strip()

        if brain in SUPPORTED_BRAINS:
            jarvis.config["active_brain"] = brain
            if key:
                jarvis.config["brain_keys"][brain] = [key]
            if model:
                jarvis.config["brain_models"][brain] = model
            jarvis.save_config()
            return jsonify({"success": True, "message": f"Active brain switched to {SUPPORTED_BRAINS[brain]['name']}."})
        return jsonify({"success": False, "message": "Invalid brain provider."})

def run_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

def start_app():
    srv = threading.Thread(target=run_flask, daemon=True)
    srv.start()
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
    start_app()
