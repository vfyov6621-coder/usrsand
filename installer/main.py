"""
Zaya UserBot — Установщик и менеджер обновлений
"""
import os
import sys
import json
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import tkinter as tk
from tkinter import messagebox, filedialog


# ═══ Настройки ════════════════════════════════════════════════════════
REPO_OWNER = "vfyov6621-coder"
REPO_NAME = "usrsand"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "ZayaUserBot")
CONFIG_NAME = "installer_config.json"

# ═══ Цвета ════════════════════════════════════════════════════════════
C = {
    "bg":       "#0d0d1a",
    "panel":    "#13132a",
    "input":    "#1a1a3a",
    "text":     "#e8e8f0",
    "dim":      "#6a6aa0",
    "accent":   "#7c3aed",
    "accent2":  "#6d28d9",
    "green":    "#10b981",
    "red":      "#ef4444",
    "orange":   "#f59e0b",
    "border":   "#28284a",
}


# ═══ Утилиты ══════════════════════════════════════════════════════════

def _resource(relative):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def _run_git(cwd, *args):
    try:
        r = subprocess.run(
            ["git"] + list(args), cwd=cwd,
            capture_output=True, text=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def _pip_install(req_file):
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file],
            capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return r.returncode, r.stderr.strip()[-200:] if r.stderr else ""
    except Exception as e:
        return -1, str(e)


def _github_api(url, token=None):
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"token {token}")
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", "ZayaInstaller/1.0")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


# ═══ Конфиг ══════════════════════════════════════════════════════════

class Config:
    def __init__(self):
        self.path = os.path.join(DEFAULT_DIR, CONFIG_NAME)
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, k, d=None):
        return self.data.get(k, d)

    def set(self, k, v):
        self.data[k] = v
        self.save()


# ═══ Приложение ════════════════════════════════════════════════════════

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Zaya UserBot")
        self.root.geometry("900x620")
        self.root.configure(bg=C["bg"])
        self.root.resizable(False, False)

        # по центру экрана
        self.root.update_idletasks()
        sx = (self.root.winfo_screenwidth() - 900) // 2
        sy = (self.root.winfo_screenheight() - 620) // 2
        self.root.geometry(f"900x620+{sx}+{sy}")

        # конфиг
        self.cfg = Config()
        self.installed = self.cfg.get("installed", False)
        self.current_sha = self.cfg.get("current_sha", "")

        # tkinter vars
        self.v_dir = tk.StringVar(value=self.cfg.get("install_dir", DEFAULT_DIR))
        self.v_api_id = tk.StringVar(value=self.cfg.get("api_id", ""))
        self.v_api_hash = tk.StringVar(value=self.cfg.get("api_hash", ""))
        self.v_phone = tk.StringVar(value=self.cfg.get("phone", ""))
        self.v_session = tk.StringVar(value=self.cfg.get("session_string", ""))
        self.v_token = tk.StringVar(value=self.cfg.get("github_token", ""))
        self.v_auto = tk.BooleanVar(value=self.cfg.get("auto_update", False))
        self.v_interval = tk.StringVar(value=self.cfg.get("update_interval", "1:00"))

        self._bg_photo = None
        self.running = True
        self._auto_thread = None

        self._build()
        self._draw_bg()

        # начальная вкладка
        if self.installed:
            self._tab("updates")

        if self.installed and self.v_auto.get():
            self._start_auto()

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ─── UI ──────────────────────────────────────────────────────

    def _build(self):
        # canvas фон
        self.cv = tk.Canvas(self.root, width=900, height=620, highlightthickness=0, bg=C["bg"])
        self.cv.pack(fill="both", expand=True)

        # панель
        self.pn = tk.Frame(self.cv, bg=C["panel"])
        self.cv.create_window(450, 310, window=self.pn, width=840, height=570)

        # заголовок
        hdr = tk.Frame(self.pn, bg=C["panel"])
        hdr.pack(fill="x", padx=24, pady=(20, 8))
        tk.Label(hdr, text="Zaya UserBot", bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 22, "bold")).pack(side="left")
        tk.Label(hdr, text=f"v{self.cfg.get('installed_ver', '1.0')}", bg=C["panel"],
                 fg=C["dim"], font=("Segoe UI", 10)).pack(side="left", padx=(12, 0))

        # табы
        self._build_tabs()

        # контент
        self.body = tk.Frame(self.pn, bg=C["panel"])
        self.body.pack(fill="both", expand=True, padx=24, pady=4)

        self.frm_install = tk.Frame(self.body, bg=C["panel"])
        self.frm_updates = tk.Frame(self.body, bg=C["panel"])
        self._build_install()
        self._build_updates()
        self._build_log()

    def _build_tabs(self):
        tf = tk.Frame(self.pn, bg=C["panel"])
        tf.pack(fill="x", padx=24, pady=(0, 2))

        self.btn_tab1 = tk.Label(tf, text="  Установка  ", bg=C["accent"], fg="#fff",
                                  font=("Segoe UI", 11, "bold"), cursor="hand2", padx=12, pady=5)
        self.btn_tab1.pack(side="left", padx=(0, 4))
        self.btn_tab1.bind("<Button-1>", lambda e: self._tab("install"))

        self.btn_tab2 = tk.Label(tf, text="  Обновления  ", bg=C["input"], fg=C["dim"],
                                  font=("Segoe UI", 11), cursor="hand2", padx=12, pady=5)
        self.btn_tab2.pack(side="left")
        self.btn_tab2.bind("<Button-1>", lambda e: self._tab("updates"))

    def _tab(self, name):
        if name == "install":
            self.btn_tab1.configure(bg=C["accent"], fg="#fff", font=("Segoe UI", 11, "bold"))
            self.btn_tab2.configure(bg=C["input"], fg=C["dim"], font=("Segoe UI", 11))
            self.frm_install.pack(fill="both", expand=True)
            self.frm_updates.pack_forget()
        else:
            self.btn_tab2.configure(bg=C["accent"], fg="#fff", font=("Segoe UI", 11, "bold"))
            self.btn_tab1.configure(bg=C["input"], fg=C["dim"], font=("Segoe UI", 11))
            self.frm_updates.pack(fill="both", expand=True)
            self.frm_install.pack_forget()

    # ─── хелперы виджетов ────────────────────────────────────────

    def _row(self, parent, label_text, var, show=None, browse=False):
        r = tk.Frame(parent, bg=C["panel"])
        r.pack(fill="x", pady=4)
        tk.Label(r, text=label_text, bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 10), anchor="w", width=22).pack(side="left")
        e = tk.Entry(r, textvariable=var, bg=C["input"], fg=C["text"],
                     insertbackground=C["text"], font=("Segoe UI", 10),
                     relief="flat", highlightthickness=1,
                     highlightcolor=C["accent"], highlightbackground=C["border"],
                     show=show)
        e.pack(side="left", fill="x", expand=True, padx=(6, 0))
        if browse:
            b = tk.Label(r, text="Обзор", bg=C["input"], fg=C["dim"],
                         font=("Segoe UI", 9), cursor="hand2", padx=8, pady=2)
            b.pack(side="right", padx=(6, 0))
            b.bind("<Button-1>", lambda e: self._browse(var))
        return r

    def _btn(self, parent, text, cmd, color=None):
        color = color or C["accent"]
        b = tk.Label(parent, text=text, bg=color, fg="#fff",
                     font=("Segoe UI", 10, "bold"), cursor="hand2", padx=18, pady=7)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=C["accent2"] if color == C["accent"] else color))
        b.bind("<Leave>", lambda e: b.configure(bg=color))
        return b

    def _browse(self, var):
        p = filedialog.askdirectory(initialdir=var.get())
        if p:
            var.set(p)

    # ─── вкладка Установка ────────────────────────────────────────

    def _build_install(self):
        f = self.frm_install
        self._row(f, "📁 Папка:", self.v_dir, browse=True)
        self._row(f, "🔑 API ID:", self.v_api_id)
        self._row(f, "🔑 API Hash:", self.v_api_hash)
        self._row(f, "📱 Телефон:", self.v_phone)
        self._row(f, "🔗 Session String:", self.v_session, show="•")

        tk.Label(f, text="API ID/Hash — my.telegram.org  |  Session — если уже авторизованы",
                 bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8), anchor="w"
                 ).pack(fill="x", pady=(2, 8))

        br = tk.Frame(f, bg=C["panel"])
        br.pack(fill="x", pady=(4, 0))
        self._btn(br, "  ⚡ Установить  ", self._do_install, C["green"]).pack(side="left")

    # ─── вкладка Обновления ──────────────────────────────────────

    def _build_updates(self):
        f = self.frm_updates

        # статус
        sf = tk.Frame(f, bg=C["input"], padx=14, pady=10)
        sf.pack(fill="x", pady=(0, 8))

        self.lbl_status = tk.Label(sf, text="✅ Установлена", bg=C["input"], fg=C["green"],
                                   font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_status.pack(anchor="w")
        self.lbl_ver = tk.Label(sf, text=f"SHA: {self.current_sha[:7] if self.current_sha else '?'}",
                               bg=C["input"], fg=C["dim"], font=("Segoe UI", 10), anchor="w")
        self.lbl_ver.pack(anchor="w")

        # кнопки
        br = tk.Frame(f, bg=C["panel"])
        br.pack(fill="x", pady=(0, 10))
        self._btn(br, "  🔍 Проверить  ", self._do_check).pack(side="left", padx=(0, 8))
        self._btn(br, "  📥 Обновить  ", self._do_pull, C["green"]).pack(side="left")

        # разделитель
        tk.Frame(f, bg=C["border"], height=1).pack(fill="x", pady=8)

        # автообновление
        tk.Label(f, text="🔄 Автообновление", bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x", pady=(0, 8))

        cb = tk.Checkbutton(f, text="Включить автообновление", variable=self.v_auto,
                            bg=C["panel"], fg=C["text"], selectcolor=C["input"],
                            activebackground=C["panel"], activeforeground=C["text"],
                            font=("Segoe UI", 10), command=self._toggle_auto)
        cb.pack(anchor="w")

        ir = tk.Frame(f, bg=C["panel"])
        ir.pack(fill="x", pady=6)
        tk.Label(ir, text="⏱ Интервал (ЧЧ:ММ):", bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 10), width=22, anchor="w").pack(side="left")
        tk.Entry(ir, textvariable=self.v_interval, bg=C["input"], fg=C["text"],
                 insertbackground=C["text"], font=("Segoe UI", 10), width=8,
                 relief="flat", highlightthickness=1,
                 highlightcolor=C["accent"], highlightbackground=C["border"]).pack(side="left", padx=(6, 0))
        tk.Label(ir, text="  (напр. 1:30 = 1ч 30мин)", bg=C["panel"], fg=C["dim"],
                 font=("Segoe UI", 9)).pack(side="left", padx=6)

        # github token (для приватного репо)
        self._row(f, "🔑 GitHub Token:", self.v_token)

        self._btn(f, "  💾 Сохранить  ", self._save_settings, C["input"]).pack(anchor="w", pady=(10, 0))

    # ─── лог ──────────────────────────────────────────────────────

    def _build_log(self):
        lf = tk.Frame(self.pn, bg=C["input"])
        lf.pack(fill="x", padx=24, pady=(8, 20))
        tk.Label(lf, text="Лог", bg=C["input"], fg=C["dim"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(5, 0))
        self.log = tk.Text(lf, height=5, bg=C["bg"], fg=C["text"],
                           font=("Consolas", 9), relief="flat", bd=0,
                           insertbackground=C["text"], wrap="word")
        self.log.pack(fill="x", padx=10, pady=(4, 10))
        self.log.configure(state="disabled")

    def _msg(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ─── фон ─────────────────────────────────────────────────────

    def _draw_bg(self):
        bg = _resource("background.png")
        if os.path.exists(bg) and HAS_PIL:
            try:
                img = Image.open(bg).resize((900, 620), Image.LANCZOS).convert("RGBA")
                ov = Image.new("RGBA", img.size, (13, 13, 26, 195))
                img = Image.alpha_composite(img, ov)
                self._bg_photo = ImageTk.PhotoImage(img)
                self.cv.create_image(0, 0, anchor="nw", image=self._bg_photo)
                return
            except Exception:
                pass
        # градиент
        for i in range(620):
            ratio = i / 620
            r = int(13 + ratio * 10)
            g = int(13 + ratio * 6)
            b = int(26 + ratio * 18)
            self.cv.create_line(0, i, 900, i, fill=f"#{r:02x}{g:02x}{b:02x}")

    # ═══ Логика установки ═══════════════════════════════════════════

    def _do_install(self):
        if not self.v_api_id.get().strip():
            messagebox.showwarning("Внимание", "Введите API ID")
            return
        if not self.v_api_hash.get().strip():
            messagebox.showwarning("Внимание", "Введите API Hash")
            return
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        d = self.v_dir.get().strip()
        self._msg("🚀 Начинаем установку...")

        # git clone / pull
        git_dir = os.path.join(d, ".git")
        if os.path.exists(git_dir):
            self._msg("📂 Репо существует — git pull...")
            c, o, e = _run_git(d, "pull", "origin", "main")
            if c != 0:
                self._msg(f"❌ git pull: {e}")
                return
        else:
            os.makedirs(d, exist_ok=True)
            self._msg(f"📂 Клонирую в {d}...")
            c, o, e = _run_git(os.path.dirname(d.rstrip("/\\")), "clone", REPO_URL,
                                os.path.basename(d.rstrip("/\\")))
            if c != 0:
                self._msg(f"❌ clone: {e}")
                return

        self._msg("✅ Репозиторий готов")

        # SHA
        c, sha, _ = _run_git(d, "rev-parse", "HEAD")
        if c == 0:
            self.current_sha = sha
            self.cfg.set("current_sha", sha)

        # зависимости
        req = os.path.join(d, "requirements.txt")
        if os.path.exists(req):
            self._msg("📦 Установка зависимостей...")
            rc, err = _pip_install(req)
            if rc == 0:
                self._msg("✅ Зависимости установлены")
            else:
                self._msg(f"⚠ pip: {err}")

        # .env
        env = os.path.join(d, ".env")
        lines = [
            f"API_ID={self.v_api_id.get().strip()}",
            f"API_HASH={self.v_api_hash.get().strip()}",
        ]
        if self.v_phone.get().strip():
            lines.append(f"PHONE={self.v_phone.get().strip()}")
        if self.v_session.get().strip():
            lines.append(f"SESSION_STRING={self.v_session.get().strip()}")
        with open(env, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self._msg("✅ .env создан")

        # ярлыки
        self._shortcuts(d)

        # сохранить конфиг
        self.cfg.set("install_dir", d)
        self.cfg.set("api_id", self.v_api_id.get().strip())
        self.cfg.set("api_hash", self.v_api_hash.get().strip())
        self.cfg.set("installed", True)
        self.cfg.set("installed_ver", "3.0")
        self.installed = True

        self._msg("🎉 Установка завершена!")
        self.root.after(600, lambda: self._tab("updates"))

    def _shortcuts(self, d):
        bat = f'@echo off\r\ncd /d "{d}"\r\ntitle Zaya UserBot\r\npython main.py\r\npause\r\n'
        with open(os.path.join(d, "start.bat"), "w", encoding="utf-8") as f:
            f.write(bat)
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            with open(os.path.join(desktop, "ZayaUserBot.bat"), "w", encoding="utf-8") as f:
                f.write(bat)
            self._msg("✅ Ярлык на рабочем столе")
        except Exception:
            pass

    # ═══ Логика обновлений ═══════════════════════════════════════════

    def _do_check(self):
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        self._msg("🔍 Проверяю обновления...")
        token = self.v_token.get().strip() or None
        data = _github_api(API_URL, token)
        if data is None:
            self._msg("❌ Не удалось подключиться к GitHub")
            return

        rsha = data.get("sha", "")
        date = data.get("commit", {}).get("committer", {}).get("date", "?")
        msg = data.get("commit", {}).get("message", "?").split("\n")[0]

        self._msg(f"📡 Удалённая: {rsha[:7]}  |  {date}")
        self._msg(f"📝 {msg}")

        if self.current_sha and rsha == self.current_sha:
            self._msg("✅ У вас последняя версия")
        else:
            self._msg("📦 Доступно обновление!")

    def _do_pull(self):
        d = self.v_dir.get().strip()
        if not os.path.exists(os.path.join(d, ".git")):
            messagebox.showwarning("Внимание", "Сначала установите бота")
            return
        threading.Thread(target=self._pull, daemon=True).start()

    def _pull(self):
        d = self.v_dir.get().strip()
        self._msg("📥 Обновляю...")
        _run_git(d, "stash")
        c, o, e = _run_git(d, "pull", "origin", "main")
        if c != 0:
            self._msg(f"❌ pull: {e}")
            _run_git(d, "stash", "pop")
            return
        _run_git(d, "stash", "pop")
        self._msg("✅ Код обновлён")

        req = os.path.join(d, "requirements.txt")
        if os.path.exists(req):
            self._msg("📦 pip install...")
            _pip_install(req)

        c, sha, _ = _run_git(d, "rev-parse", "HEAD")
        if c == 0:
            self.current_sha = sha
            self.cfg.set("current_sha", sha)
            self.root.after(0, lambda: self.lbl_ver.configure(text=f"SHA: {sha[:7]}"))

        self._msg("🎉 Обновление завершено!")

    # ═══ Автообновление ═════════════════════════════════════════════

    def _toggle_auto(self):
        if self.v_auto.get():
            self._start_auto()
        else:
            self._msg("⏹ Автообновление выключено")

    def _start_auto(self):
        if self._auto_thread and self._auto_thread.is_alive():
            return
        self._auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self._auto_thread.start()
        self._msg("🔄 Автообновление запущено")

    def _auto_loop(self):
        while self.running and self.v_auto.get():
            try:
                parts = self.v_interval.get().strip().split(":")
                h = int(parts[0])
                m = int(parts[1]) if len(parts) > 1 else 0
                secs = max(h * 3600 + m * 60, 300)
            except Exception:
                secs = 3600

            for _ in range(secs):
                if not self.running or not self.v_auto.get():
                    return
                time.sleep(1)

            if self.running and self.v_auto.get():
                self.root.after(0, lambda: self._msg("🔄 Авто-проверка..."))
                token = self.v_token.get().strip() or None
                data = _github_api(API_URL, token)
                if data:
                    rsha = data.get("sha", "")
                    if self.current_sha and rsha != self.current_sha:
                        self.root.after(0, lambda: self._msg("📦 Найдено обновление!"))
                        self._pull()

    def _save_settings(self):
        self.cfg.set("auto_update", self.v_auto.get())
        self.cfg.set("update_interval", self.v_interval.get())
        t = self.v_token.get().strip()
        if t:
            self.cfg.set("github_token", t)
        self._msg("💾 Настройки сохранены")
        if self.v_auto.get():
            self._start_auto()

    # ═══ Выход ═══════════════════════════════════════════════════════

    def _quit(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = App()
    app.run()
