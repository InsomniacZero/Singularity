"""
Ngrok Tunnel Manager for Singularity Unified AI Gateway
Exposes port 9000 securely to the public internet for remote mobile/tablet use.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

import sys

NGROK_INSPECT_URL = "http://127.0.0.1:4040/api/tunnels"
DEFAULT_PORT = 9000


def check_ngrok_installed() -> bool:
    """Check if the ngrok executable is in the system PATH."""
    return shutil.which("ngrok") is not None


def get_ngrok_config_path() -> Path:
    """Return the default path for ngrok.yml across platforms."""
    candidates = []
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "ngrok" / "ngrok.yml")
        candidates.append(Path.home() / "AppData" / "Local" / "ngrok" / "ngrok.yml")
    candidates.append(Path.home() / ".config" / "ngrok" / "ngrok.yml")
    candidates.append(Path.home() / ".ngrok2" / "ngrok.yml")

    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def has_authtoken() -> bool:
    """Check if an authtoken has already been configured in ngrok.yml."""
    cfg = get_ngrok_config_path()
    if not cfg.exists():
        return False
    try:
        content = cfg.read_text(encoding="utf-8")
        return "authtoken:" in content and len(content.strip()) > 15
    except Exception:
        return False


def get_tunnel_status() -> Dict[str, Any]:
    """Check if an ngrok tunnel is currently online and return its public URL."""
    installed = check_ngrok_installed()
    has_token = has_authtoken()

    if not installed:
        return {
            "status": "not_installed",
            "installed": False,
            "url": None,
            "public_url": None,
            "api_url": None,
            "has_authtoken": False,
            "message": "ngrok is not installed. Download from https://ngrok.com/download",
        }

    try:
        resp = httpx.get(NGROK_INSPECT_URL, timeout=1.5)
        if resp.status_code == 200:
            data = resp.json()
            tunnels = data.get("tunnels", [])
            if tunnels:
                https_tunnels = [t for t in tunnels if t.get("proto") == "https" or str(t.get("public_url", "")).startswith("https")]
                t = https_tunnels[0] if https_tunnels else tunnels[0]
                public_url = (t.get("public_url") or "").rstrip("/")
                return {
                    "status": "online",
                    "installed": True,
                    "has_authtoken": True,
                    "url": public_url,
                    "public_url": public_url,
                    "api_url": f"{public_url}/v1",
                    "chat_completions_url": f"{public_url}/v1/chat/completions",
                    "proto": t.get("proto", "https"),
                    "name": t.get("name", "singularity-access"),
                }
    except Exception:
        pass

    return {
        "status": "offline",
        "installed": installed,
        "has_authtoken": has_token,
        "url": None,
        "public_url": None,
        "api_url": None,
        "chat_completions_url": None,
        "message": "Tunnel is offline. Click Start Tunnel to expose Singularity to the internet.",
    }


def start_tunnel(port: int = DEFAULT_PORT) -> Dict[str, Any]:
    """Spawn an ngrok tunnel for the specified local port."""
    current = get_tunnel_status()
    if current.get("status") == "online":
        return current

    if not check_ngrok_installed():
        return {
            "status": "error",
            "message": "ngrok is not installed on this system. Please install ngrok first.",
        }

    # Launch ngrok process detached from parent across Windows and Unix
    try:
        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["preexec_fn"] = os.setpgrp

        subprocess.Popen(["ngrok", "http", str(port)], **popen_kwargs)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to spawn ngrok process: {e}",
        }

    # Poll inspect endpoint for up to 8 seconds
    start_time = time.time()
    while time.time() - start_time < 8.0:
        time.sleep(0.5)
        status = get_tunnel_status()
        if status.get("status") == "online":
            return status

    return {
        "status": "error",
        "message": "Tunnel process started, but connection timed out. Check your ngrok authtoken or terminal logs.",
    }


def stop_tunnel() -> Dict[str, Any]:
    """Stop all active ngrok tunnels by terminating the process."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/IM", "ngrok.exe", "/T"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(["pkill", "-x", "ngrok"], check=False)
        time.sleep(0.5)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return get_tunnel_status()


def save_authtoken(token: str) -> Dict[str, Any]:
    """Configure a new ngrok authtoken."""
    clean_token = (token or "").strip()
    if not clean_token:
        return {"status": "error", "message": "Authtoken cannot be empty."}

    try:
        res = subprocess.run(
            ["ngrok", "config", "add-authtoken", clean_token],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return {
                "status": "ok",
                "message": "ngrok authtoken configured successfully!",
                "has_authtoken": True,
            }
        else:
            return {
                "status": "error",
                "message": res.stderr.strip() or "Failed to add authtoken via ngrok CLI.",
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}
