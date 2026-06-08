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
import tempfile
import shutil
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
RELEASES_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
INSTALLER_VER = "1.1"
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "ZayaUserBot")
CONFIG_NAME = "installer_config.json"

# ═══ Цвета — чистый тёмный, без фиолетового нейросетевого ═══════════
C = {
    "bg":       "#1e1e2e",
    "panel":    "#282840",
    "card":     "#313150",
    "input":    "#2a2a48",
    "text":     "#cdd6f4",
    "dim":      "#7f849c",
    "accent":   "#89b4fa",
    "accent2":  "#74c7ec",
    "green":    "#a6e3a1",
    "red":      "#f38ba8",
    "orange":   "#fab387",
    "yellow":   "#f9e2af",
    "border":   "#45475a",
}


# ═══ Утилиты ══════════════════════════════════════════════════════════

def _resource(relative):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def _run_git(cwd, *args):
    try:
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(
            ["git"] + list(args), cwd=cwd,
            capture_output=True, text=True, timeout=120, **kw,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def _pip_install(req_file):
    try:
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file],
            capture_output=True, text=True, timeout=300, **kw,
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


def _download_file(url, dest, token=None):
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"token {token}")
        req.add_header("User-Agent", "ZayaInstaller/1.0")
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
        return True
    except Exception:
        return False


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
        self.root.geometry("960x640")
        self.root.configure(bg=C["bg"])
        self.root.resizable(False, False)

        # иконка окна
        self._set_icon()

        sx = (self.root.winfo_screenwidth() - 960) // 2
        sy = (self.root.winfo_screenheight() - 640) // 2
        self.root.geometry(f"960x640+{sx}+{sy}")

        self.cfg = Config()
        self.installed = self.cfg.get("installed", False)
        self.current_sha = self.cfg.get("current_sha", "")

        self.v_dir = tk.StringVar(value=self.cfg.get("install_dir", DEFAULT_DIR))
        self.v_api_id = tk.StringVar(value=self.cfg.get("api_id", ""))
        self.v_api_hash = tk.StringVar(value=self.cfg.get("api_hash", ""))
        self.v_phone = tk.StringVar(value=self.cfg.get("phone", ""))
        self.v_session = tk.StringVar(value=self.cfg.get("session_string", ""))
        self.v_token = tk.StringVar(value=self.cfg.get("github_token", ""))
        self.v_auto = tk.BooleanVar(value=self.cfg.get("auto_update", False))
        self.v_interval = tk.StringVar(value=self.cfg.get("update_interval", "1:00"))
        self.v_inst_auto = tk.BooleanVar(value=self.cfg.get("installer_auto_update", True))

        self._bg_photo = None
        self.running = True
        self._auto_thread = None
        self._tab_name = "install"

        self._build()
        self._draw_bg()

        if self.installed:
            self._switch("updates")

        if self.installed and self.v_auto.get():
            self._start_auto()

        # проверить обновление установщика при старте
        if self.v_inst_auto.get():
            threading.Thread(target=self._check_installer_update, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ─── иконка ───────────────────────────────────────────────────

    def _set_icon(self):
        """Set window icon from .ico or .png."""
        ico = _resource("icon.ico")
        png = _resource("icon.png")
        try:
            if os.path.exists(ico):
                self.root.iconbitmap(ico)
                return
        except Exception:
            pass
        try:
            if os.path.exists(png) and HAS_PIL:
                from PIL import ImageTk
                self._icon_photo = ImageTk.PhotoImage(Image.open(png).resize((32, 32), Image.LANCZOS))
                self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ─── UI ──────────────────────────────────────────────────────

    def _build(self):
        self.cv = tk.Canvas(self.root, width=960, height=640, highlightthickness=0, bg=C["bg"])
        self.cv.pack(fill="both", expand=True)

        self.pn = tk.Frame(self.cv, bg=C["panel"])
        self.cv.create_window(480, 320, window=self.pn, width=900, height=600)

        # заголовок
        hdr = tk.Frame(self.pn, bg=C["panel"])
        hdr.pack(fill="x", padx=28, pady=(20, 6))

        tk.Label(hdr, text="Zaya", bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 24, "bold")).pack(side="left")
        tk.Label(hdr, text=" UserBot", bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 24)).pack(side="left")

        ver_text = f"bot v{self.cfg.get('installed_ver', '?')}  |  installer v{INSTALLER_VER}"
        tk.Label(hdr, text=ver_text, bg=C["panel"], fg=C["dim"],
                 font=("Segoe UI", 9)).pack(side="right")

        # табы
        self._build_tabs()

        # контент
        self.body = tk.Frame(self.pn, bg=C["panel"])
        self.body.pack(fill="both", expand=True, padx=28, pady=4)

        self.frm_install = tk.Frame(self.body, bg=C["panel"])
        self.frm_updates = tk.Frame(self.body, bg=C["panel"])
        self._build_install()
        self._build_updates()
        self._build_log()

    def _build_tabs(self):
        tf = tk.Frame(self.pn, bg=C["panel"])
        tf.pack(fill="x", padx=28, pady=(0, 4))

        self.tabs = {}
        for key, label in [("install", "Установка"), ("updates", "Обновления")]:
            is_active = key == "install"
            bg = C["card"] if is_active else C["panel"]
            fg = C["text"] if is_active else C["dim"]
            btn = tk.Label(tf, text=f"  {label}  ", bg=bg, fg=fg,
                           font=("Segoe UI", 10), cursor="hand2", padx=14, pady=6,
                           relief="flat", bd=0)
            btn.pack(side="left", padx=(0, 4))
            btn.bind("<Button-1>", lambda e, k=key: self._switch(k))
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=C["card"]))
            btn.bind("<Leave>", lambda e, b=btn, k=key: b.configure(
                bg=C["card"] if self._tab_name == k else C["panel"]))
            self.tabs[key] = btn

    def _switch(self, name):
        self._tab_name = name
        for k, btn in self.tabs.items():
            if k == name:
                btn.configure(bg=C["card"], fg=C["text"])
                btn.pack(side="left", padx=(0, 4))
            else:
                btn.configure(bg=C["panel"], fg=C["dim"])
                btn.pack(side="left", padx=(0, 4))
        if name == "install":
            self.frm_install.pack(fill="both", expand=True)
            self.frm_updates.pack_forget()
        else:
            self.frm_updates.pack(fill="both", expand=True)
            self.frm_install.pack_forget()

    # ─── виджеты ────────────────────────────────────────────────

    def _row(self, parent, label_text, var, show=None, browse=False, browse_file=False):
        r = tk.Frame(parent, bg=C["panel"])
        r.pack(fill="x", pady=3)
        tk.Label(r, text=label_text, bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 10), anchor="w", width=20).pack(side="left")
        e = tk.Entry(r, textvariable=var, bg=C["input"], fg=C["text"],
                     insertbackground=C["text"], font=("Segoe UI", 10),
                     relief="flat", highlightthickness=1, bd=4,
                     highlightcolor=C["accent"], highlightbackground=C["border"],
                     show=show)
        e.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._bind_clipboard(e)
        if browse:
            b = tk.Label(r, text="Обзор", bg=C["card"], fg=C["dim"],
                         font=("Segoe UI", 9), cursor="hand2", padx=10, pady=3)
            b.pack(side="right", padx=(8, 0))
            b.bind("<Button-1>", lambda e: self._browse(var))
            b.bind("<Enter>", lambda e: b.configure(fg=C["text"]))
            b.bind("<Leave>", lambda e: b.configure(fg=C["dim"]))
        elif browse_file:
            b = tk.Label(r, text="Файл", bg=C["card"], fg=C["dim"],
                         font=("Segoe UI", 9), cursor="hand2", padx=10, pady=3)
            b.pack(side="right", padx=(8, 0))
            b.bind("<Button-1>", lambda e: self._browse_file(var))
            b.bind("<Enter>", lambda e: b.configure(fg=C["text"]))
            b.bind("<Leave>", lambda e: b.configure(fg=C["dim"]))
        return r

    def _btn(self, parent, text, cmd, color=None):
        color = color or C["accent"]
        fg = C["bg"] if color in (C["green"], C["yellow"], C["orange"]) else "#fff"
        if color == C["accent"]:
            fg = C["bg"]
        b = tk.Label(parent, text=text, bg=color, fg=fg,
                     font=("Segoe UI", 10, "bold"), cursor="hand2", padx=20, pady=6)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=C["accent2"]))
        b.bind("<Leave>", lambda e: b.configure(bg=color))
        return b

    def _card(self, parent):
        f = tk.Frame(parent, bg=C["card"], padx=16, pady=12)
        f.pack(fill="x", pady=(0, 10))
        return f

    def _bind_clipboard(self, widget):
        """Bind clipboard shortcuts to a widget (fixes Ctrl+V on Canvas).

        Works with both Latin and Cyrillic keyboard layouts.
        """
        widget.bind("<Button-1>", lambda e, w=widget: w.focus_set(), add="+")
        # латиница
        widget.bind("<Control-v>", lambda e, w=widget: w.event_generate("<<Paste>>"))
        widget.bind("<Control-c>", lambda e, w=widget: w.event_generate("<<Copy>>"))
        widget.bind("<Control-x>", lambda e, w=widget: w.event_generate("<<Cut>>"))
        widget.bind("<Control-a>", lambda e, w=widget: w.select_range(0, "end"))
        # кириллица (русская раскладка Ctrl+В/С/Ч/Ф)
        widget.bind("<Control-в>", lambda e, w=widget: w.event_generate("<<Paste>>"))
        widget.bind("<Control-с>", lambda e, w=widget: w.event_generate("<<Copy>>"))
        widget.bind("<Control-ч>", lambda e, w=widget: w.event_generate("<<Cut>>"))
        widget.bind("<Control-ф>", lambda e, w=widget: w.select_range(0, "end"))

    def _browse(self, var):
        p = filedialog.askdirectory(initialdir=var.get())
        if p:
            var.set(p)

    def _browse_file(self, var):
        p = filedialog.askopenfilename(
            title="Выбрать файл",
            initialdir=os.path.dirname(var.get()) if var.get() else None,
        )
        if p:
            var.set(p)

    # ─── вкладка Установка ────────────────────────────────────────

    def _build_install(self):
        f = self.frm_install

        card = self._card(f)
        self._row(card, "Папка установки:", self.v_dir, browse=True)
        self._row(card, "API ID:", self.v_api_id)
        self._row(card, "API Hash:", self.v_api_hash)
        self._row(card, "Телефон:", self.v_phone)
        self._row(card, "Session String:", self.v_session, show="*", browse_file=True)

        tk.Label(f, text="API ID/Hash — my.telegram.org  |  Session — если авторизованы",
                 bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8), anchor="w"
                 ).pack(fill="x", pady=(2, 6))

        br = tk.Frame(f, bg=C["panel"])
        br.pack(fill="x", pady=(2, 0))
        self._btn(br, "  Установить  ", self._do_install, C["green"]).pack(side="left")

    # ─── вкладка Обновления ──────────────────────────────────────

    def _build_updates(self):
        f = self.frm_updates

        # статус бота
        card1 = self._card(f)
        tk.Label(card1, text="Обновления бота", bg=C["card"], fg=C["accent"],
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w", pady=(0, 6))

        sr = tk.Frame(card1, bg=C["card"])
        sr.pack(fill="x", pady=(0, 8))
        self.lbl_status = tk.Label(sr, text="Не установлена", bg=C["card"], fg=C["orange"],
                                   font=("Segoe UI", 10), anchor="w")
        self.lbl_status.pack(anchor="w")
        self.lbl_ver = tk.Label(sr, text="SHA: —", bg=C["card"], fg=C["dim"],
                               font=("Segoe UI", 9), anchor="w")
        self.lbl_ver.pack(anchor="w")

        br = tk.Frame(card1, bg=C["card"])
        br.pack(fill="x")
        self._btn(br, "  Проверить  ", self._do_check).pack(side="left", padx=(0, 8))
        self._btn(br, "  Обновить  ", self._do_pull, C["green"]).pack(side="left")

        # разделитель
        tk.Frame(f, bg=C["border"], height=1).pack(fill="x", pady=6)

        # автообновление
        card2 = self._card(f)
        tk.Label(card2, text="Автообновление бота", bg=C["card"], fg=C["accent"],
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w", pady=(0, 6))

        cb = tk.Checkbutton(card2, text="Проверять и обновлять автоматически",
                            variable=self.v_auto,
                            bg=C["card"], fg=C["text"], selectcolor=C["input"],
                            activebackground=C["card"], activeforeground=C["text"],
                            font=("Segoe UI", 10), command=self._toggle_auto)
        cb.pack(anchor="w")

        ir = tk.Frame(card2, bg=C["card"])
        ir.pack(fill="x", pady=8)
        tk.Label(ir, text="Интервал (Ч:М):", bg=C["card"], fg=C["text"],
                 font=("Segoe UI", 10), anchor="w").pack(side="left")
        e_interval = tk.Entry(ir, textvariable=self.v_interval, bg=C["input"], fg=C["text"],
                 insertbackground=C["text"], font=("Segoe UI", 10), width=7,
                 relief="flat", highlightthickness=1, bd=4,
                 highlightcolor=C["accent"], highlightbackground=C["border"])
        e_interval.pack(side="left", padx=(8, 0))
        self._bind_clipboard(e_interval)
        tk.Label(ir, text="  напр. 1:30 = 1ч 30мин", bg=C["card"], fg=C["dim"],
                 font=("Segoe UI", 9)).pack(side="left", padx=8)

        self._row(card2, "GitHub Token:", self.v_token)

        self._btn(card2, "  Сохранить  ", self._save_settings, C["input"]).pack(anchor="w", pady=(8, 0))

        # разделитель
        tk.Frame(f, bg=C["border"], height=1).pack(fill="x", pady=6)

        # самообновление установщика
        card3 = self._card(f)
        tk.Label(card3, text="Обновление установщика", bg=C["card"], fg=C["accent"],
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w", pady=(0, 6))

        self.lbl_inst_status = tk.Label(card3, text=f"Текущая версия: v{INSTALLER_VER}",
                                        bg=C["card"], fg=C["dim"], font=("Segoe UI", 10), anchor="w")
        self.lbl_inst_status.pack(anchor="w")

        ibr = tk.Frame(card3, bg=C["card"])
        ibr.pack(fill="x", pady=(8, 0))
        self._btn(ibr, "  Проверить  ", self._do_check_installer).pack(side="left", padx=(0, 8))
        self._btn(ibr, "  Обновить установщик  ", self._do_update_installer, C["orange"]).pack(side="left")

    # ─── лог ──────────────────────────────────────────────────────

    def _build_log(self):
        lf = tk.Frame(self.pn, bg=C["card"])
        lf.pack(fill="x", padx=28, pady=(6, 20))
        tk.Label(lf, text="Лог", bg=C["card"], fg=C["dim"],
                 font=("Segoe UI", 9), anchor="w").pack(anchor="w", padx=12, pady=(6, 0))
        self.log = tk.Text(lf, height=4, bg=C["bg"], fg=C["text"],
                           font=("Consolas", 9), relief="flat", bd=0,
                           insertbackground=C["text"], wrap="word")
        self.log.pack(fill="x", padx=12, pady=(4, 10))
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
                img = Image.open(bg).resize((960, 640), Image.LANCZOS).convert("RGBA")
                ov = Image.new("RGBA", img.size, (30, 30, 46, 210))
                img = Image.alpha_composite(img, ov)
                self._bg_photo = ImageTk.PhotoImage(img)
                self.cv.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg_img")
                self.cv.tag_lower("bg_img")  # фон ПОД панелью с UI
                return
            except Exception:
                pass
        # простая заливка
        self.cv.configure(bg=C["bg"])

    # ═══ Установка ════════════════════════════════════════════════════

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
        self._msg("Начинаем установку...")

        git_dir = os.path.join(d, ".git")
        if os.path.exists(git_dir):
            self._msg("Репо существует — git pull...")
            c, o, e = _run_git(d, "pull", "origin", "main")
            if c != 0:
                self._msg(f"git pull ошибка: {e}")
                return
        else:
            os.makedirs(d, exist_ok=True)
            self._msg(f"Клонирую в {d}...")
            c, o, e = _run_git(os.path.dirname(d.rstrip("/\\")), "clone", REPO_URL,
                                os.path.basename(d.rstrip("/\\")))
            if c != 0:
                self._msg(f"clone ошибка: {e}")
                return

        self._msg("Репозиторий готов")

        c, sha, _ = _run_git(d, "rev-parse", "HEAD")
        if c == 0:
            self.current_sha = sha
            self.cfg.set("current_sha", sha)

        req = os.path.join(d, "requirements.txt")
        if os.path.exists(req):
            self._msg("Установка зависимостей...")
            rc, err = _pip_install(req)
            if rc == 0:
                self._msg("Зависимости установлены")
            else:
                self._msg(f"pip: {err}")

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
        self._msg(".env создан")

        self._shortcuts(d)

        self.cfg.set("install_dir", d)
        self.cfg.set("api_id", self.v_api_id.get().strip())
        self.cfg.set("api_hash", self.v_api_hash.get().strip())
        self.cfg.set("installed", True)
        self.cfg.set("installed_ver", "3.0")
        self.installed = True

        self.root.after(0, lambda: self.lbl_status.configure(text="Установлена", fg=C["green"]))
        self.root.after(0, lambda: self.lbl_ver.configure(text=f"SHA: {self.current_sha[:7]}"))
        self._msg("Установка завершена!")
        self.root.after(600, lambda: self._switch("updates"))

    def _shortcuts(self, d):
        bat = f'@echo off\r\ncd /d "{d}"\r\ntitle Zaya UserBot\r\npython main.py\r\npause\r\n'
        with open(os.path.join(d, "start.bat"), "w", encoding="utf-8") as f:
            f.write(bat)
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            with open(os.path.join(desktop, "ZayaUserBot.bat"), "w", encoding="utf-8") as f:
                f.write(bat)
            self._msg("Ярлык на рабочем столе")
        except Exception:
            pass

    # ═══ Обновления бота ══════════════════════════════════════════════

    def _do_check(self):
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        self._msg("Проверяю обновления бота...")
        token = self.v_token.get().strip() or None
        data = _github_api(API_URL, token)
        if data is None:
            self._msg("Не удалось подключиться к GitHub")
            return

        rsha = data.get("sha", "")
        msg = data.get("commit", {}).get("message", "?").split("\n")[0]

        self._msg(f"Удалённая: {rsha[:7]} | {msg}")

        if self.current_sha and rsha == self.current_sha:
            self._msg("Последняя версия")
        else:
            self._msg("Доступно обновление!")

    def _do_pull(self):
        d = self.v_dir.get().strip()
        if not os.path.exists(os.path.join(d, ".git")):
            messagebox.showwarning("Внимание", "Сначала установите бота")
            return
        threading.Thread(target=self._pull, daemon=True).start()

    def _pull(self):
        d = self.v_dir.get().strip()
        self._msg("Обновляю...")
        _run_git(d, "stash")
        c, o, e = _run_git(d, "pull", "origin", "main")
        if c != 0:
            self._msg(f"pull ошибка: {e}")
            _run_git(d, "stash", "pop")
            return
        _run_git(d, "stash", "pop")
        self._msg("Код обновлён")

        req = os.path.join(d, "requirements.txt")
        if os.path.exists(req):
            self._msg("pip install...")
            _pip_install(req)

        c, sha, _ = _run_git(d, "rev-parse", "HEAD")
        if c == 0:
            self.current_sha = sha
            self.cfg.set("current_sha", sha)
            self.root.after(0, lambda: self.lbl_ver.configure(text=f"SHA: {sha[:7]}"))

        self._msg("Обновление завершено!")

    # ═══ Автообновление бота ══════════════════════════════════════════

    def _toggle_auto(self):
        if self.v_auto.get():
            self._start_auto()
        else:
            self._msg("Автообновление выключено")

    def _start_auto(self):
        if self._auto_thread and self._auto_thread.is_alive():
            return
        self._auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self._auto_thread.start()
        self._msg("Автообновление запущено")

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
                self.root.after(0, lambda: self._msg("Авто-проверка..."))
                token = self.v_token.get().strip() or None
                data = _github_api(API_URL, token)
                if data:
                    rsha = data.get("sha", "")
                    if self.current_sha and rsha != self.current_sha:
                        self.root.after(0, lambda: self._msg("Найдено обновление!"))
                        self._pull()

    def _save_settings(self):
        self.cfg.set("auto_update", self.v_auto.get())
        self.cfg.set("update_interval", self.v_interval.get())
        t = self.v_token.get().strip()
        if t:
            self.cfg.set("github_token", t)
        self._msg("Настройки сохранены")
        if self.v_auto.get():
            self._start_auto()

    # ═══ Самообновление установщика (.exe) ═══════════════════════════

    def _check_installer_update(self):
        token = self.v_token.get().strip() or None
        data = _github_api(RELEASES_URL, token)
        if data is None:
            return

        tag = data.get("tag_name", "")
        assets = data.get("assets", [])
        exe_asset = None
        for a in assets:
            name = a.get("name", "")
            if name.endswith(".exe"):
                exe_asset = a
                break

        if not exe_asset:
            return

        remote_ver = tag.lstrip("v")
        if remote_ver != INSTALLER_VER:
            download_url = exe_asset.get("browser_download_url", "")
            self.root.after(0, lambda: self.lbl_inst_status.configure(
                text=f"Доступна версия: {tag} (у вас {INSTALLER_VER})", fg=C["orange"]))
            self.cfg.set("_installer_download_url", download_url)
            self.cfg.set("_installer_new_ver", remote_ver)
        else:
            self.root.after(0, lambda: self.lbl_inst_status.configure(
                text=f"Текущая версия: v{INSTALLER_VER} (последняя)", fg=C["green"]))

    def _do_check_installer(self):
        self._msg("Проверяю обновление установщика...")
        threading.Thread(target=self._check_installer_update, daemon=True).start()

    def _do_update_installer(self):
        download_url = self.cfg.get("_installer_download_url", "")
        if not download_url:
            self._msg("Сначала нажмите 'Проверить' для обновления установщика")
            return
        if not messagebox.askyesno("Обновление",
                f"Установщик скачает новую версию и запустит её.\nТекущий процесс закроется.\n\nПродолжить?"):
            return
        threading.Thread(target=self._update_installer, daemon=True).start()

    def _update_installer(self):
        self._msg("Скачиваю обновление установщика...")
        token = self.v_token.get().strip() or None

        # скачать во временный файл
        tmp = os.path.join(tempfile.gettempdir(), "ZayaUserBot_Setup_new.exe")
        if _download_file(self.cfg.get("_installer_download_url", ""), tmp, token):
            self._msg("Скачано! Запускаю новую версию...")

            # путь к текущему .exe
            if getattr(sys, "frozen", False):
                current_exe = sys.executable
            else:
                current_exe = os.path.abspath(__file__)

            # батник для замены
            bat_path = os.path.join(tempfile.gettempdir(), "zaya_update.bat")
            new_name = os.path.basename(current_exe)
            bat = f'@echo off\r\ntimeout /t 2 /nobreak >nul\r\ncopy /y "{tmp}" "{current_exe}"\r\nstart "" "{current_exe}"\r\ndel "{bat_path}"\r\n'
            with open(bat_path, "w") as f:
                f.write(bat)

            self.running = False
            self.root.destroy()

            # запустить батник (заменит .exe и перезапустит)
            subprocess.Popen(
                bat_path,
                shell=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
        else:
            self._msg("Ошибка скачивания обновления")

    # ═══ Выход ═══════════════════════════════════════════════════════

    def _quit(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = App()
    app.run()
