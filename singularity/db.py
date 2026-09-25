#!/usr/bin/env python3
"""
Singularity Unified Credential Database Manager
Zero-dependency SQLite store for multi-account stacking across all 6 AI providers:
ChatGPT, Claude, Gemini, GLM, Kimi, and Grok.

Designed to be 100% self-contained within the Singularity repository for
effortless cross-device portability (PC, Android Termux, laptops).
"""

import base64
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MODULE_DIR = Path(__file__).resolve().parent
DATA_DIR = MODULE_DIR / "data"
DB_PATH = DATA_DIR / "singularity.db"
ROOT_DIR = MODULE_DIR.parent


def get_db_connection() -> sqlite3.Connection:
    """Ensure data directory exists and return an SQLite connection."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables and indexes."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                identifier TEXT NOT NULL,
                name TEXT,
                token TEXT NOT NULL,
                plan TEXT DEFAULT 'free',
                status TEXT DEFAULT 'active',
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, identifier)
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_status 
            ON credentials(provider, status);
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()


# ==============================================================================
# Token & Credential Parsers
# ==============================================================================

def _clean_jwt_string(raw: str) -> str:
    """Extract and unwrap clean JWT string from raw input (JSON, quotes, cookies, or Bearer prefix)."""
    if not raw:
        return ""
    t = raw.strip().replace("\r", "")
    # Strip wrapping quotes
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    # If JSON object, look for refresh_token, kimi-refresh-token, access_token, token, or value
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            data = json.loads(t)
            if isinstance(data, dict):
                cand = (
                    data.get("refresh_token")
                    or data.get("kimi-refresh-token")
                    or data.get("access_token")
                    or data.get("token")
                    or data.get("value")
                )
                if cand:
                    t = str(cand).strip()
            elif isinstance(data, list) and data:
                if isinstance(data[0], str):
                    t = data[0].strip()
                elif isinstance(data[0], dict):
                    cand = (
                        data[0].get("refresh_token")
                        or data[0].get("kimi-refresh-token")
                        or data[0].get("access_token")
                        or data[0].get("token")
                        or data[0].get("value")
                    )
                    if cand:
                        t = str(cand).strip()
        except Exception:
            pass
    # Strip Bearer prefix if present
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    
    # If string contains a valid 3-part JWT pattern, extract it cleanly
    jwt_match = re.search(r"(eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)", t)
    if jwt_match:
        return jwt_match.group(1).strip()

    return t.strip().strip('"').strip("'")


def _decode_jwt_payload(token_str: str) -> Optional[Dict[str, Any]]:
    """Safely decode JWT payload without verification."""
    try:
        clean = _clean_jwt_string(token_str)
        parts = clean.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        pass
    return None


def parse_credential(provider: str, raw: str) -> Optional[Dict[str, Any]]:
    """Parse raw user input into structured credential object."""
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None

    # 1. ChatGPT
    if provider == "chatgpt":
        # Check if JSON dump
        if raw.startswith("{") or raw.startswith("["):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    user = data.get("user", {}) if isinstance(data.get("user"), dict) else {}
                    email = user.get("email") or data.get("email")
                    name = user.get("name") or data.get("name")
                    access_token = data.get("accessToken") or data.get("access_token")
                    session_token = data.get("sessionToken") or data.get("session_token")
                    plan = data.get("account", {}).get("planType") or data.get("plan_type") or data.get("type") or "free"

                    if not access_token and "token" in data:
                        access_token = data["token"]

                    if not email and access_token:
                        jwt = _decode_jwt_payload(access_token)
                        if jwt:
                            email = jwt.get("https://api.openai.com/profile", {}).get("email") or jwt.get("email")
                            if not name:
                                name = jwt.get("https://api.openai.com/profile", {}).get("name")

                    token = access_token or session_token or raw
                    identifier = (email or f"user_{token[:12]}").strip().lower()
                    name = name or (email.split("@")[0] if email and "@" in email else "ChatGPT User")
                    return {
                        "provider": "chatgpt",
                        "identifier": identifier,
                        "name": name,
                        "token": raw,
                        "plan": plan,
                        "status": "active",
                        "metadata": json.dumps({"email": email, "access_token": access_token or "", "session_token": session_token or ""}),
                    }
            except Exception:
                pass

        # Raw JWT / token
        jwt = _decode_jwt_payload(raw)
        email = None
        name = "ChatGPT User"
        if jwt:
            email = jwt.get("https://api.openai.com/profile", {}).get("email") or jwt.get("email")
            name = jwt.get("https://api.openai.com/profile", {}).get("name") or name

        identifier = (email or f"chatgpt_{raw[:15]}").strip().lower()
        if email and "@" in email:
            name = email.split("@")[0]
        return {
            "provider": "chatgpt",
            "identifier": identifier,
            "name": name,
            "token": raw,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"email": email, "access_token": raw, "session_token": ""}),
        }

    # 2. Kimi
    elif provider == "kimi":
        raw = _clean_jwt_string(raw)
        # Check if cookie / env format: KIMI_TOKEN=..., kimi-refresh-token=..., refresh_token=...
        cookie_m = re.search(r"(?:kimi[-_]?refresh[-_]?token|refresh[-_]?token|kimi[-_]?token)=([^\s;]+)", raw, re.IGNORECASE)
        if cookie_m:
            raw = _clean_jwt_string(cookie_m.group(1))
        elif "KIMI_TOKEN=" in raw:
            m = re.search(r"KIMI_TOKEN=([^\s]+)", raw)
            if m:
                raw = _clean_jwt_string(m.group(1))

        jwt = _decode_jwt_payload(raw)
        sub = None
        device_id = None
        exp = None
        name = "Kimi Account"
        if jwt:
            sub = jwt.get("sub") or jwt.get("abstract_user_id") or jwt.get("jti")
            device_id = jwt.get("device_id")
            exp = jwt.get("exp")
            region = jwt.get("region", "global")
            name = f"Kimi ({sub[:8]})" if sub else f"Kimi ({region})"

        identifier = sub or f"kimi_{raw[-16:]}"
        return {
            "provider": "kimi",
            "identifier": identifier,
            "name": name,
            "token": raw,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"sub": sub, "device_id": device_id, "exp": exp}),
        }

    # 3. Claude
    elif provider == "claude":
        # Check if sessionKey: "..."
        m = re.search(r'sessionKey:\s*"([^"]+)"', raw)
        key = m.group(1).strip() if m else raw.strip()
        if key.startswith('"') and key.endswith('"'):
            key = key[1:-1].strip()

        identifier = key
        masked = key[:12] + "..." + key[-6:] if len(key) > 20 else key
        return {
            "provider": "claude",
            "identifier": identifier,
            "name": f"Claude ({masked})",
            "token": key,
            "plan": "pro",
            "status": "active",
            "metadata": json.dumps({"sessionKey": key}),
        }

    # 4. Grok
    elif provider == "grok":
        sso_m = re.search(r"sso=([^;]+)", raw)
        uid_m = re.search(r"x-userid=([^;]+)", raw)
        sso = sso_m.group(1).strip() if sso_m else ""
        uid = uid_m.group(1).strip() if uid_m else ""

        identifier = uid or (sso[:20] if sso else raw[:30])
        name = f"Grok ({uid[:8]})" if uid else "Grok Account"
        return {
            "provider": "grok",
            "identifier": identifier,
            "name": name,
            "token": raw,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"sso": sso, "uid": uid}),
        }

    # 5. Gemini
    elif provider == "gemini":
        psid_m = re.search(r"__Secure-1PSID=([^;]+)", raw)
        psidts_m = re.search(r"__Secure-1PSIDTS=([^;]+)", raw)
        psid = psid_m.group(1).strip() if psid_m else raw[:25]
        has_psidts = bool(psidts_m)
        metadata = {
            "psid": psid,
            "has_psidts": has_psidts,
        }
        if not has_psidts:
            metadata["warning"] = "Missing __Secure-1PSIDTS cookie. Google requires both __Secure-1PSID and __Secure-1PSIDTS for full authentication & image generation."
        identifier = psid
        return {
            "provider": "gemini",
            "identifier": identifier,
            "name": f"Gemini ({psid[:8]}...)",
            "token": raw,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps(metadata),
        }

    # 6. GLM
    elif provider == "glm":
        token = raw.strip()
        identifier = token[:30]
        return {
            "provider": "glm",
            "identifier": identifier,
            "name": f"GLM ({token[:8]}...)",
            "token": token,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({}),
        }

    # 7. DeepSeek
    elif provider == "deepseek":
        raw_str = raw.strip()
        email = ""
        token = raw_str
        uid = ""
        if raw_str.startswith("{"):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    email = d.get("email", "")
                    token = d.get("token") or d.get("userToken") or d.get("user_token") or d.get("value") or raw_str
                    uid = d.get("uid") or ""
            except Exception:
                pass

        if not email and token:
            jwt = _decode_jwt_payload(token)
            if jwt:
                email = jwt.get("email") or ""
                uid = jwt.get("sub") or jwt.get("uid") or ""

        identifier = (email or uid or f"ds_{token[:20]}").strip().lower()
        name = f"DeepSeek ({identifier[:8]})" if not email else email.split("@")[0]
        return {
            "provider": "deepseek",
            "identifier": identifier,
            "name": name,
            "token": token,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"email": email, "uid": uid}),
        }

    # 8. Qwen (Alibaba Cloud)
    elif provider in ("qwen", "tongyi"):
        raw_str = raw.strip()
        email = ""
        token = raw_str
        uid = ""
        cookies = ""
        if raw_str.startswith("{"):
            try:
                d = json.loads(raw_str)
                if isinstance(d, dict):
                    email = d.get("email", "")
                    token = (
                        d.get("token")
                        or d.get("userToken")
                        or d.get("user_token")
                        or d.get("value")
                        or d.get("access_token")
                        or raw_str
                    )
                    uid = d.get("uid") or d.get("id") or ""
                    cookies = d.get("cookies") or d.get("cookie") or ""
            except Exception:
                pass
        elif ";" in raw_str and ("eyJ" in raw_str or "x5sec" in raw_str):
            parts = [p.strip() for p in raw_str.split(";", 1)]
            if parts[0].startswith("eyJ"):
                token = parts[0]
                cookies = parts[1]
            elif "x5sec" in parts[0] or "bx-v" in parts[0]:
                cookies = parts[0]
                token = parts[1]

        if not email and token:
            jwt = _decode_jwt_payload(token)
            if jwt:
                email = jwt.get("email") or ""
                uid = jwt.get("id") or jwt.get("sub") or jwt.get("uid") or jwt.get("user_id") or ""

        identifier = (email or uid or f"qwen_{token[:20]}").strip().lower()
        name = f"Qwen ({identifier[:8]})" if not email else email.split("@")[0]
        return {
            "provider": "qwen",
            "identifier": identifier,
            "name": name,
            "token": token,
            "plan": "free",
            "status": "active",
            "metadata": json.dumps({"email": email, "uid": uid, "cookies": cookies}),
        }

    return None


# ==============================================================================
# CRUD Operations
# ==============================================================================

def get_accounts(provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve accounts from database."""
    init_db()
    with get_db_connection() as conn:
        if provider:
            rows = conn.execute(
                "SELECT * FROM credentials WHERE provider = ? ORDER BY id DESC",
                (provider,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM credentials ORDER BY provider, id DESC"
            ).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "provider": r["provider"],
                "identifier": r["identifier"],
                "name": r["name"] or r["identifier"],
                "token": r["token"],
                "plan": r["plan"] or "free",
                "status": r["status"] or "active",
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
        return results


def save_account(
    provider: str,
    raw_credential: str,
    name: Optional[str] = None,
    plan: Optional[str] = None,
    status: str = "active",
) -> Tuple[bool, str]:
    """Insert or update a single credential with deduplication."""
    init_db()
    parsed = parse_credential(provider, raw_credential)
    if not parsed:
        return False, "Failed to parse credential"

    identifier = parsed["identifier"]
    final_name = name or parsed["name"]
    final_plan = plan or parsed["plan"]
    token = parsed["token"]
    metadata = parsed["metadata"]

    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO credentials (provider, identifier, name, token, plan, status, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(provider, identifier) DO UPDATE SET
                name = excluded.name,
                token = excluded.token,
                plan = excluded.plan,
                status = excluded.status,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP
        """, (provider, identifier, final_name, token, final_plan, status, metadata))
        conn.commit()

    return True, f"Saved account '{final_name}' for {provider}."


def save_accounts(provider: str, items: List[str]) -> Tuple[int, int]:
    """Bulk stack credentials with deduplication. Returns (added_or_updated, failed)."""
    init_db()
    success = 0
    failed = 0
    for item in items:
        if not item or not item.strip():
            continue
        ok, _ = save_account(provider, item.strip())
        if ok:
            success += 1
        else:
            failed += 1

    return success, failed


def remove_account(provider: str, identifier: Optional[str] = None, account_id: Optional[int] = None) -> bool:
    """Delete a specific account by identifier or database ID."""
    init_db()
    with get_db_connection() as conn:
        if account_id is not None:
            cur = conn.execute(
                "DELETE FROM credentials WHERE provider = ? AND id = ?",
                (provider, account_id),
            )
        elif identifier:
            ident_clean = identifier.strip()
            num_id = int(ident_clean) if ident_clean.isdigit() else -1
            cur = conn.execute(
                "DELETE FROM credentials WHERE provider = ? AND (identifier = ? OR token = ? OR id = ?)",
                (provider, ident_clean, ident_clean, num_id),
            )
        else:
            return False

        deleted = cur.rowcount > 0
        conn.commit()

    return deleted


def clear_accounts(provider: str) -> int:
    """Remove all accounts for a given provider."""
    init_db()
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM credentials WHERE provider = ?", (provider,))
        count = cur.rowcount
        conn.commit()
    return count


_ROTATION_INDEX: Dict[str, int] = {}

def get_next_token(provider: str) -> Optional[str]:
    """Return the next active account's token in round-robin order."""
    init_db()
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT token FROM credentials WHERE provider = ? AND status = 'active' ORDER BY id ASC",
            (provider,),
        ).fetchall()
        if not rows:
            return None
        idx = _ROTATION_INDEX.get(provider, 0) % len(rows)
        token = rows[idx]["token"]
        _ROTATION_INDEX[provider] = (idx + 1) % len(rows)
        return token



# ==============================================================================
# Cross-Device Export & Import (1-Click Sync)
# ==============================================================================

def get_stats() -> Dict[str, Any]:
    """Return summary counts of accounts per provider."""
    init_db()
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT provider, status, COUNT(*) as count 
            FROM credentials 
            GROUP BY provider, status
        """).fetchall()

    grouped: Dict[str, Dict[str, int]] = {}
    total = 0
    for r in rows:
        p = r["provider"]
        st = r["status"]
        cnt = r["count"]
        total += cnt
        if p not in grouped:
            grouped[p] = {"total": 0, "active": 0, "disabled": 0}
        grouped[p]["total"] += cnt
        if st == "active":
            grouped[p]["active"] += cnt
        else:
            grouped[p]["disabled"] += cnt

    return {
        "total_accounts": total,
        "providers": grouped,
    }


def export_all_json() -> Dict[str, Any]:
    """Export all stored credentials across all providers as a portable JSON structure."""
    accounts = get_accounts()
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "chatgpt": [],
        "claude": [],
        "gemini": [],
        "glm": [],
        "kimi": [],
        "grok": [],
    }

    for acc in accounts:
        p = acc["provider"]
        if p not in grouped:
            grouped[p] = []
        grouped[p].append({
            "identifier": acc["identifier"],
            "name": acc["name"],
            "token": acc["token"],
            "plan": acc["plan"],
            "status": acc["status"],
            "metadata": acc["metadata"],
        })

    return {
        "version": 1,
        "format": "singularity_credentials",
        "exported_at": int(time.time()),
        "total_accounts": len(accounts),
        "providers": grouped,
    }


def import_all_json(data: Any) -> Dict[str, Any]:
    """Import credentials from a JSON dictionary or file dump."""
    init_db()
    if isinstance(data, str):
        data = json.loads(data)

    if not isinstance(data, dict):
        raise ValueError("Invalid credentials payload: expected JSON object")

    providers_data = data.get("providers") if "providers" in data else data
    imported_count = 0

    for provider, acc_list in providers_data.items():
        if not isinstance(acc_list, list):
            continue
        for acc in acc_list:
            token = acc.get("token") or acc.get("raw") or (acc if isinstance(acc, str) else None)
            if not token:
                continue
            name = acc.get("name") if isinstance(acc, dict) else None
            plan = acc.get("plan") if isinstance(acc, dict) else None
            status = acc.get("status", "active") if isinstance(acc, dict) else "active"
            ok, _ = save_account(provider, token, name=name, plan=plan, status=status)
            if ok:
                imported_count += 1

    return {
        "status": "ok",
        "imported_accounts": imported_count,
        "message": f"Successfully imported {imported_count} accounts across providers.",
    }


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a configuration value from settings table."""
    init_db()
    with get_db_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    """Insert or update a configuration value in settings table."""
    init_db()
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, str(value)))
        conn.commit()


def get_all_settings() -> Dict[str, str]:
    """Retrieve all persistent key-value configuration settings."""
    init_db()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def get_model_settings(model: str) -> Dict[str, Any]:
    """Retrieve customized settings (thinking_budget, max_tokens, etc.) for a model."""
    if not model:
        return {}
    m = model.lower().strip()
    raw = get_setting(f"model_cfg:{m}")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    # If model has provider prefix or path (e.g. claude/claude-3-7-sonnet or models/gemini-...)
    if "/" in m:
        base = m.split("/")[-1]
        raw = get_setting(f"model_cfg:{base}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
    return {}


def set_model_settings(model: str, cfg: Dict[str, Any]) -> None:
    """Persist customized settings (thinking_budget, max_tokens, etc.) for a model."""
    if not model:
        return
    m = model.lower().strip()
    clean_cfg = dict(cfg)
    clean_cfg["model"] = m
    clean_cfg["updated_at"] = time.time()
    set_setting(f"model_cfg:{m}", json.dumps(clean_cfg))


def delete_model_settings(model: str) -> None:
    """Delete customized model settings for a model, reverting to defaults."""
    if not model:
        return
    m = model.lower().strip()
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (f"model_cfg:{m}",))
        if "/" in m:
            base = m.split("/")[-1]
            conn.execute("DELETE FROM settings WHERE key = ?", (f"model_cfg:{base}",))
        conn.commit()


def get_all_model_settings() -> Dict[str, Dict[str, Any]]:
    """Retrieve all model settings overrides across all registered models."""
    all_s = get_all_settings()
    res = {}
    for k, v in all_s.items():
        if k.startswith("model_cfg:"):
            m = k[len("model_cfg:"):]
            try:
                res[m] = json.loads(v)
            except Exception:
                pass
    return res


if __name__ == "__main__":
    init_db()
    all_acc = get_accounts()
    print(f"[+] Singularity Credential DB initialized. Stored accounts: {len(all_acc)}")
    for a in all_acc:
        print(f"  - [{a['provider'].upper()}] {a['name']} ({a['identifier']})")

