import os
import sys
import json
import datetime
import re
import random
import threading
import time
from urllib.parse import quote_plus
from flask import Flask, render_template, request, jsonify

# ----------------- CONFIG & PATHS -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "jarvis_config.json")
HISTORY_FILE = os.path.join(BASE_DIR, "jarvis_memory.json")
LOG_DIR = os.path.join(BASE_DIR, "chat_logs")

os.makedirs(LOG_DIR, exist_ok=True)

try:
    import requests
except ImportError:
    requests = None

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "brain_mode": "hybrid",
    "voice_enabled": True,
    "auto_search": True,
    "local_llm_url": "http://127.0.0.1:11434",
    "local_model": "",
    "max_history_turns": 12
}

# ----------------- JARVIS ENGINE -----------------
class JarvisCore:
    def __init__(self):
        self.config = self.load_config()
        self.history = self.load_history()

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
                    data = json.load(f)
                if isinstance(data, list):
                    return data
            except Exception:
                pass
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
