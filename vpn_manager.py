#!/usr/bin/env python3
"""
VPN manager for sandusr.
Manages VLESS/VMess/Trojan/SS/Hysteria2 connections via xray-core.

Usage:
    python vpn_manager.py <command> [args]

Commands:
    connect              Parse saved link, generate config, start xray
    disconnect           Stop xray, clear PROXY from .env
    status               Show VPN status
    is_running           Print 1 if running, 0 otherwise
    set_link_from_file   Read link from a temp file, validate, save
    get_link             Print saved VPN link (or NONE)
    get_proto            Print detected protocol name (or NONE)
    download             Download xray-core to vpn/
    test                 Test SOCKS5 port + Telegram reachability
"""

import sys
import os
import json
import base64
import subprocess
import time
import socket
import zipfile
import shutil
import urllib.request
from urllib.parse import urlparse, parse_qs, unquote

# ─── Paths ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VPN_DIR = os.path.join(BASE_DIR, "vpn")
CFG_FILE = os.path.join(BASE_DIR, "launcher.cfg")
LINK_FILE = os.path.join(BASE_DIR, "vpn_link.txt")
XRAY_CONFIG_FILE = os.path.join(VPN_DIR, "config.json")
XRAY_PID_FILE = os.path.join(VPN_DIR, "xray.pid")
XRAY_EXE = os.path.join(VPN_DIR, "xray.exe")


# ─── Config helpers ──────────────────────────────────────────────────

def load_cfg():
    cfg = {}
    if os.path.exists(CFG_FILE):
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg


def save_cfg(updates):
    existing = load_cfg()
    existing.update(updates)
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f"{k}={v}\n")


def get_link():
    if os.path.exists(LINK_FILE):
        with open(LINK_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def set_link(link):
    with open(LINK_FILE, "w", encoding="utf-8") as f:
        f.write(link.strip())


def find_xray():
    if os.path.isfile(XRAY_EXE):
        return XRAY_EXE
    try:
        r = subprocess.run(["where", "xray"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass
    return None


# ─── Link parsers ────────────────────────────────────────────────────

def parse_vless(link):
    parsed = urlparse(link)
    if parsed.scheme.lower() != "vless":
        return None
    params = parse_qs(parsed.query)
    network = params.get("type", ["tcp"])[0]
    security = params.get("security", ["none"])[0]

    result = {
        "protocol": "vless",
        "uuid": parsed.username or "",
        "address": parsed.hostname or "",
        "port": parsed.port or 443,
        "name": unquote(parsed.fragment) if parsed.fragment else "",
        "network": network,
        "security": security,
        "flow": params.get("flow", [""])[0],
        "fingerprint": params.get("fp", [""])[0],
        "sni": params.get("sni", [""])[0],
        "alpn": params.get("alpn", [""])[0],
    }

    if network == "ws":
        result["ws_path"] = unquote(params.get("path", ["/"])[0])
        result["ws_host"] = params.get("host", [""])[0]
    elif network == "grpc":
        result["grpc_service"] = params.get("serviceName", [""])[0]
    elif network == "tcp":
        result["tcp_header_type"] = params.get("headerType", ["none"])[0]

    if security == "reality":
        result["reality_pbk"] = params.get("pbk", [""])[0]
        result["reality_sid"] = params.get("sid", [""])[0]
    return result


def parse_vmess(link):
    b64 = link[8:].strip()
    b64 += "=" * (4 - len(b64) % 4) if len(b64) % 4 else ""
    try:
        decoded = base64.b64decode(b64).decode("utf-8")
    except Exception:
        try:
            b64 = b64.replace("-", "+").replace("_", "/")
            b64 += "=" * (4 - len(b64) % 4) if len(b64) % 4 else ""
            decoded = base64.b64decode(b64).decode("utf-8")
        except Exception as e:
            print(f"ERR: VMess decode error: {e}")
            return None
    try:
        data = json.loads(decoded)
    except Exception as e:
        print(f"ERR: VMess json error: {e}")
        return None

    network = data.get("net", "tcp")
    result = {
        "protocol": "vmess",
        "uuid": data.get("id", ""),
        "address": data.get("add", ""),
        "port": int(data.get("port", 443)),
        "name": data.get("ps", ""),
        "network": network,
        "security": data.get("tls", "none"),
        "alter_id": int(data.get("aid", 0)),
        "fingerprint": data.get("fp", ""),
        "sni": data.get("sni", ""),
        "alpn": data.get("alpn", ""),
    }
    if network == "ws":
        result["ws_path"] = data.get("path", "/")
        result["ws_host"] = data.get("host", "")
    elif network == "grpc":
        result["grpc_service"] = data.get("path", "")
    return result


def parse_trojan(link):
    parsed = urlparse(link)
    if parsed.scheme.lower() not in ("trojan", "trojan-go"):
        return None
    params = parse_qs(parsed.query)
    network = params.get("type", ["tcp"])[0]

    result = {
        "protocol": "trojan",
        "password": unquote(parsed.username or parsed.password or ""),
        "address": parsed.hostname or "",
        "port": parsed.port or 443,
        "name": unquote(parsed.fragment) if parsed.fragment else "",
        "network": network,
        "security": params.get("security", ["tls"])[0],
        "sni": params.get("sni", [""])[0],
        "fingerprint": params.get("fp", [""])[0],
        "alpn": params.get("alpn", [""])[0],
        "allow_insecure": params.get("allowInsecure", ["0"])[0] == "1",
    }
    if network == "ws":
        result["ws_path"] = unquote(params.get("path", ["/"])[0])
        result["ws_host"] = params.get("host", [""])[0]
    elif network == "grpc":
        result["grpc_service"] = params.get("serviceName", [""])[0]
    return result


def parse_ss(link):
    rest = link[5:]
    name = ""
    if "#" in rest:
        rest, frag = rest.rsplit("#", 1)
        name = unquote(frag)

    if "@" in rest:
        b64_part, server_part = rest.rsplit("@", 1)
        try:
            b64_part += "=" * (4 - len(b64_part) % 4) if len(b64_part) % 4 else ""
            decoded = base64.b64decode(b64_part).decode("utf-8")
            method, password = decoded.split(":", 1)
        except Exception:
            method, password = b64_part.split(":", 1)
        host, port = (server_part.rsplit(":", 1) + ["443"])[:2]
        port = int(port)
    else:
        try:
            rest += "=" * (4 - len(rest) % 4) if len(rest) % 4 else ""
            decoded = base64.b64decode(rest).decode("utf-8")
            mp, hp = decoded.rsplit("@", 1)
            method, password = mp.split(":", 1)
            host, port = hp.rsplit(":", 1)
            port = int(port)
        except Exception as e:
            print(f"ERR: SS decode error: {e}")
            return None

    return {
        "protocol": "ss",
        "method": method,
        "password": password,
        "address": host,
        "port": port,
        "name": name,
    }


def parse_hy2(link):
    parsed = urlparse(link)
    if parsed.scheme.lower() not in ("hysteria2", "hy2"):
        return None
    params = parse_qs(parsed.query)
    return {
        "protocol": "hysteria2",
        "password": unquote(parsed.username or ""),
        "address": parsed.hostname or "",
        "port": parsed.port or 443,
        "name": unquote(parsed.fragment) if parsed.fragment else "",
        "sni": params.get("sni", [""])[0],
        "insecure": params.get("insecure", ["0"])[0] == "1",
    }


def parse_link(link):
    """Auto-detect protocol and parse. Returns dict or None."""
    link = link.strip()
    if not link:
        return None
    for prefix, parser in [
        ("vless://", parse_vless),
        ("vmess://", parse_vmess),
        ("trojan://", parse_trojan),
        ("ss://", parse_ss),
        ("hysteria2://", parse_hy2),
        ("hy2://", parse_hy2),
    ]:
        if link.lower().startswith(prefix):
            return parser(link)
    print(f"ERR: Unknown protocol: {link[:30]}...")
    return None


# ─── Xray config generator ───────────────────────────────────────────

def _stream_settings(p):
    """Build streamSettings from parsed config dict."""
    network = p.get("network", "tcp")
    security = p.get("security", "none")
    stream = {"network": network}

    if security == "tls":
        tls = {}
        if p.get("sni"):
            tls["serverName"] = p["sni"]
        if p.get("alpn"):
            tls["alpn"] = [a for a in p["alpn"].split(",") if a]
        if p.get("fingerprint"):
            tls["fingerprint"] = p["fingerprint"]
        if p.get("allow_insecure"):
            tls["allowInsecure"] = True
        stream["security"] = "tls"
        stream["tlsSettings"] = tls
    elif security == "reality":
        r = {}
        if p.get("sni"):
            r["serverName"] = p["sni"]
        if p.get("reality_pbk"):
            r["publicKey"] = p["reality_pbk"]
        if p.get("reality_sid"):
            r["shortId"] = p["reality_sid"]
        if p.get("fingerprint"):
            r["fingerprint"] = p["fingerprint"]
        stream["security"] = "reality"
        stream["realitySettings"] = r
    else:
        stream["security"] = "none"

    if network == "ws":
        ws = {}
        if p.get("ws_path"):
            ws["path"] = p["ws_path"]
        if p.get("ws_host"):
            ws["headers"] = {"Host": p["ws_host"]}
        stream["wsSettings"] = ws
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": p.get("grpc_service", "")}
    elif network == "tcp" and p.get("tcp_header_type") and p["tcp_header_type"] != "none":
        stream["tcpSettings"] = {"header": {"type": p["tcp_header_type"]}}

    return stream


def generate_xray_config(parsed, socks_port, http_port):
    """Generate full xray-core config JSON."""
    proto = parsed["protocol"]
    outbound = {"tag": "proxy", "protocol": proto}

    if proto == "vless":
        user = {"id": parsed["uuid"], "encryption": "none"}
        if parsed.get("flow"):
            user["flow"] = parsed["flow"]
        outbound["settings"] = {
            "vnext": [{
                "address": parsed["address"],
                "port": parsed["port"],
                "users": [user],
            }]
        }
        outbound["streamSettings"] = _stream_settings(parsed)

    elif proto == "vmess":
        outbound["settings"] = {
            "vnext": [{
                "address": parsed["address"],
                "port": parsed["port"],
                "users": [{
                    "id": parsed["uuid"],
                    "alterId": parsed.get("alter_id", 0),
                    "security": "auto",
                }],
            }]
        }
        outbound["streamSettings"] = _stream_settings(parsed)

    elif proto == "trojan":
        outbound["settings"] = {
            "servers": [{
                "address": parsed["address"],
                "port": parsed["port"],
                "password": parsed["password"],
            }]
        }
        outbound["streamSettings"] = _stream_settings(parsed)

    elif proto == "ss":
        outbound["settings"] = {
            "servers": [{
                "address": parsed["address"],
                "port": parsed["port"],
                "method": parsed["method"],
                "password": parsed["password"],
            }]
        }

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks", "port": socks_port, "listen": "127.0.0.1",
                "protocol": "socks", "settings": {"udp": True, "auth": "noauth"},
            },
            {
                "tag": "http", "port": http_port, "listen": "127.0.0.1",
                "protocol": "http", "settings": {"allowTransparent": False},
            },
        ],
        "outbounds": [
            outbound,
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "outboundTag": "direct",
                 "ip": ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12",
                         "192.168.0.0/16", "fc00::/7"]},
                {"type": "field", "outboundTag": "direct",
                 "domain": ["localhost"]},
            ],
        },
    }


# ─── Process management ──────────────────────────────────────────────

def is_xray_running():
    """Returns (running: bool, pid: int|None)."""
    if not os.path.exists(XRAY_PID_FILE):
        return False, None
    try:
        with open(XRAY_PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if sys.platform == "win32":
            r = subprocess.run(
                ["tasklist", "/fi", f"pid eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in r.stdout, pid
        else:
            os.kill(pid, 0)
            return True, pid
    except Exception:
        return False, None


def stop_xray():
    running, pid = is_xray_running()
    if not running:
        print("OK: VPN already off")
        return True
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                           capture_output=True, timeout=10)
            # Also kill any xray.exe from vpn dir
            subprocess.run(["taskkill", "/f", "/im", "xray.exe"],
                           capture_output=True, timeout=10)
        else:
            os.kill(pid, 9)
        time.sleep(0.5)
        if os.path.exists(XRAY_PID_FILE):
            os.remove(XRAY_PID_FILE)
        print("OK: VPN off")
        return True
    except Exception as e:
        print(f"ERR: stop failed: {e}")
        return False


def start_xray():
    link = get_link()
    if not link:
        print("ERR: No link set. Paste a link in VPN settings first.")
        return False

    parsed = parse_link(link)
    if not parsed:
        return False

    proto = parsed["protocol"].upper()
    print(f"OK: {proto} - {parsed['address']}:{parsed['port']}")

    xray = find_xray()
    if not xray:
        print("ERR: xray not found!")
        print("     Press [D] in VPN settings to download, or place xray.exe in vpn/")
        return False

    cfg = load_cfg()
    socks_port = int(cfg.get("VPN_SOCKS_PORT", "10808"))
    http_port = int(cfg.get("VPN_HTTP_PORT", "10809"))

    xray_cfg = generate_xray_config(parsed, socks_port, http_port)
    os.makedirs(VPN_DIR, exist_ok=True)
    with open(XRAY_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(xray_cfg, f, indent=2, ensure_ascii=False)

    stop_xray()

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore

    try:
        proc = subprocess.Popen(
            [xray, "run", "-c", XRAY_CONFIG_FILE],
            cwd=VPN_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
        with open(XRAY_PID_FILE, "w") as f:
            f.write(str(proc.pid))

        time.sleep(2)
        running, _ = is_xray_running()
        if running:
            print(f"OK: VPN connected ({proto})")
            print(f"     SOCKS5: 127.0.0.1:{socks_port}")
            print(f"     HTTP:   127.0.0.1:{http_port}")
            _update_env_proxy(socks_port)
            return True
        else:
            print("ERR: xray started but crashed. Check vpn/error.log")
            return False
    except Exception as e:
        print(f"ERR: start failed: {e}")
        return False


# ─── .env proxy management ───────────────────────────────────────────

def _update_env_proxy(socks_port):
    env_file = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_file):
        return
    proxy_line = f"PROXY=socks5://127.0.0.1:{socks_port}"
    with open(env_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("PROXY="):
            new_lines.append(proxy_line + "\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(proxy_line + "\n")
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _remove_env_proxy():
    env_file = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        if line.strip().startswith("PROXY=") and line.strip() != "PROXY=":
            new_lines.append("PROXY=\n")
        else:
            new_lines.append(line)
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


# ─── Download xray-core ──────────────────────────────────────────────

def download_xray():
    print("Fetching latest release info...")
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/XTLS/Xray-core/releases/latest"
        )
        req.add_header("User-Agent", "sandusr")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        version = data.get("tag_name", "?")
        print(f"Version: {version}")

        asset = None
        for a in data.get("assets", []):
            n = a["name"].lower()
            if "windows" in n and "64" in n and n.endswith(".zip"):
                asset = a
                break
        if not asset:
            print("ERR: No Windows 64-bit archive found in release")
            return False

        print(f"Downloading {asset['name']}...")
        zip_path = os.path.join(VPN_DIR, asset["name"])
        os.makedirs(VPN_DIR, exist_ok=True)
        urllib.request.urlretrieve(asset["browser_download_url"], zip_path)
        print(f"Downloaded: {os.path.getsize(zip_path) // 1024} KB")

        print("Extracting xray.exe...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member.lower().endswith("xray.exe"):
                    with zf.open(member) as src, open(XRAY_EXE, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    break

        os.remove(zip_path)
        if os.path.isfile(XRAY_EXE):
            print(f"OK: xray installed to {VPN_DIR}")
            return True
        print("ERR: xray.exe not found in archive")
        return False
    except Exception as e:
        print(f"ERR: Download failed: {e}")
        return False


# ─── Status display ──────────────────────────────────────────────────

def show_status():
    link = get_link()
    cfg = load_cfg()

    enabled = cfg.get("VPN_ENABLED", "0") == "1"
    auto = cfg.get("VPN_AUTO", "0") == "1"
    socks_port = cfg.get("VPN_SOCKS_PORT", "10808")
    http_port = cfg.get("VPN_HTTP_PORT", "10809")

    print(f"Enabled:    {'Yes' if enabled else 'No'}")
    print(f"Auto-conn:  {'Yes' if auto else 'No'}")
    print(f"SOCKS port: {socks_port}")
    print(f"HTTP port:  {http_port}")

    if link:
        proto = link.split("://")[0].upper() if "://" in link else "?"
        print(f"Protocol:   {proto}")
        display = link if len(link) <= 60 else link[:57] + "..."
        print(f"Link:       {display}")
    else:
        print("Link:       (none)")

    print(f"xray:       {'found' if find_xray() else 'NOT FOUND'}")
    running, pid = is_xray_running()
    print(f"Status:     {'CONNECTED (PID ' + str(pid) + ')' if running else 'disconnected'}")


# ─── CLI entry point ─────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "connect":
        sys.exit(0 if start_xray() else 1)

    elif cmd == "disconnect":
        ok = stop_xray()
        if ok:
            _remove_env_proxy()
        sys.exit(0 if ok else 1)

    elif cmd == "status":
        show_status()

    elif cmd == "is_running":
        running, _ = is_xray_running()
        print("1" if running else "0")

    elif cmd == "set_link_from_file":
        if len(sys.argv) < 3:
            print("ERR: specify file path")
            sys.exit(1)
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            link = f.read().strip()
        if not link:
            print("ERR: empty link")
            sys.exit(1)
        parsed = parse_link(link)
        if not parsed:
            sys.exit(1)
        set_link(link)
        print(f"OK: {parsed['protocol'].upper()} - {parsed['address']}:{parsed['port']}")

    elif cmd == "get_link":
        link = get_link()
        print(link if link else "NONE")

    elif cmd == "get_proto":
        link = get_link()
        if link and "://" in link:
            print(link.split("://")[0].upper())
        else:
            print("NONE")

    elif cmd == "download":
        sys.exit(0 if download_xray() else 1)

    elif cmd == "test":
        cfg = load_cfg()
        sp = int(cfg.get("VPN_SOCKS_PORT", "10808"))
        print(f"Testing SOCKS5 127.0.0.1:{sp}...")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(("127.0.0.1", sp))
            s.close()
            print("OK: SOCKS port open")
        except Exception as e:
            print(f"ERR: SOCKS port: {e}")
            sys.exit(1)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect(("149.154.167.50", 443))
            s.close()
            print("OK: Telegram reachable")
        except Exception as e:
            print(f"ERR: Telegram: {e}")
            sys.exit(1)

    else:
        print(f"ERR: unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()