#!/usr/bin/env python3
"""
Singularity Unified CLI
Cross-device command-line interface for managing Singularity AI Gateway,
account vault (SQLite), feature limits, device simulation, and inferences.

Works identically on Linux, macOS, Android (Termux), and Windows.
Zero external legacy dependencies.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure singularity directory is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import db
import providers


# ==============================================================================
# Helper Formatting Utilities
# ==============================================================================

def print_header(title: str):
    width = 70
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_table(headers: List[str], rows: List[List[str]]):
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    header_line = "  ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
    sep_line = "  ".join("-" * col_widths[i] for i in range(len(headers)))
    print(header_line)
    print(sep_line)
    for row in rows:
        print("  ".join(f"{str(val):<{col_widths[i]}}" for i, val in enumerate(row)))


# ==============================================================================
# CLI Commands
# ==============================================================================

def cmd_status(args):
    """Display gateway status, provider daemons, and account vault stats."""
    db.init_db()
    sim = providers.is_simulation_active()
    stats = db.get_stats()
    remote_host = db.get_setting("remote_host", "127.0.0.1")

    if args.json:
        data = {
            "gateway": {
                "port": 9000,
                "simulation_mode": sim,
                "remote_host": remote_host,
            },
            "vault": stats,
            "services": asyncio.run(providers.get_all_services_status()),
        }
        print(json.dumps(data, indent=2))
        return

    print_header("⚡ SINGULARITY UNIFIED GATEWAY STATUS")
    print(f"  Gateway Port     : 9000")
    print(f"  Simulation Mode  : {'ENABLED (Simulated Device)' if sim else 'OFF (Live Daemons)'}")
    print(f"  Cluster Host     : {remote_host}")
    print(f"  Database Vault   : {db.DB_PATH} ({stats['total_accounts']} accounts)")

    print_header("🤖 AI PROVIDER FLEET STATUS")
    services = asyncio.run(providers.get_all_services_status())
    headers = ["Provider", "Badge", "Port", "Host", "Status", "Latency", "Accounts"]
    rows = []
    grouped = stats.get("providers", {})
    for s in services:
        pid = s["id"]
        acc_count = grouped.get(pid, {}).get("total", 0)
        status_str = "● ONLINE" if s["running"] else "○ OFFLINE"
        if s.get("simulated"):
            status_str = "● SIMULATED"
        latency_str = f"{s['latency_ms']} ms" if s.get("latency_ms") is not None else "—"
        rows.append([
            s["name"],
            s["badge"],
            str(s["port"]),
            s["host"],
            status_str,
            latency_str,
            str(acc_count),
        ])
    print_table(headers, rows)
    print()


def cmd_limits(args):
    """Inspect remaining limits and quotas across all 6 providers."""
    db.init_db()
    data = asyncio.run(providers.get_all_limits())

    if args.json:
        print(json.dumps(data, indent=2))
        return

    print_header("📊 LIVE FEATURE LIMITS & QUOTAS ACROSS PROVIDERS")

    # 1. ChatGPT
    cg = data.get("chatgpt", {})
    accounts = cg.get("accounts", [])
    print(f"\n[1] {cg.get('title', 'ChatGPT Pool')} ({len(accounts)} accounts)")
    if accounts:
        headers = ["Account / Email", "Plan", "Status", "Images/Day", "Reasoning", "Deep Research"]
        rows = []
        for a in accounts:
            rows.append([
                a.get("email", "—"),
                a.get("type", "FREE"),
                a.get("status", "Active"),
                str(a.get("image_quota", "—")),
                str(a.get("reason_remaining", "—")),
                str(a.get("deep_research", "—")),
            ])
        print_table(headers, rows)
    else:
        print("    No ChatGPT accounts in vault. Use './singular import' or Cookie Stacker.")

    # 2. Grok
    gr = data.get("grok", {}).get("data", {})
    print(f"\n[2] Grok / xAI Quotas")
    if gr:
        print(f"    Account UID : {gr.get('account_uid', '—')}")
        im = gr.get("imagine_quota", {})
        print(f"    Pro Images  : {im.get('imagePro', {}).get('remainingQueries', '—')} queries remaining")
        print(f"    Video 720p  : {im.get('video720p', {}).get('remainingQueries', '—')} queries remaining")
        rl = gr.get("rate_limits", {})
        if isinstance(rl, dict) and rl and any(isinstance(v, dict) for v in rl.values()):
            rl_headers = ["Model / Mode", "Remaining", "Window", "Status"]
            rl_rows = []
            for mod, item in rl.items():
                if isinstance(item, dict):
                    rl_rows.append([
                        mod,
                        f"{item.get('remainingQueries', 0)} / {item.get('totalQueries', 0)}",
                        f"{round((item.get('windowSizeSeconds', 0)) / 3600)}h",
                        "Active",
                    ])
            if rl_rows:
                print_table(rl_headers, rl_rows)

    # 3. Kimi / Moonshot AI
    km = data.get("kimi", {})
    km_accounts = km.get("accounts", [])
    km_summary = km.get("summary", {})
    print(f"\n[3] {km.get('title', 'Kimi / Moonshot AI Pool')} ({len(km_accounts)} accounts)")
    if km_accounts:
        headers = ["Account / UID", "Plan / Tier", "Research Today", "Deep Res", "Ok Computer", "Slides", "Cycle Reset"]
        rows = []
        for a in km_accounts:
            rows.append([
                a.get("name") or a.get("id") or "—",
                a.get("plan", "Free"),
                str(a.get("research_today", "50 / 50")),
                str(a.get("deep_research", "1 / 1 left")),
                str(a.get("ok_computer", "3 / 3 left")),
                str(a.get("slides", "3 / 3 left")),
                str(a.get("reset_date", "Active")),
            ])
        print_table(headers, rows)
        print(f"    Pool Total: Research Today: {km_summary.get('research_queries', '—')} | Deep Res: {km_summary.get('deep_research', 0)} queries | Ok Computer: {km_summary.get('ok_computer', 0)} | Slides: {km_summary.get('slides', 0)}")
    else:
        print("    No Kimi accounts configured in vault.")

    # 4. Claude / Anthropic
    cl = data.get("claude", {})
    cl_accounts = cl.get("accounts", [])
    cl_summary = cl.get("summary", {})
    print(f"\n[4] {cl.get('title', 'Claude / Anthropic Pool')} ({len(cl_accounts)} sessions)")
    if cl_accounts:
        headers = ["Session / Name", "Plan", "Rolling Window", "Context Window", "Reasoning / CoT", "Opus Access", "Status"]
        rows = []
        for a in cl_accounts:
            rows.append([
                a.get("identifier", "—"),
                a.get("plan", "PRO"),
                str(a.get("rolling_window", "45 msgs / 5 hrs")),
                str(a.get("context_window", "200,000 tokens")),
                str(a.get("thinking_budget", "64K CoT")),
                str(a.get("opus_access", "Unlocked")),
                a.get("status", "Active"),
            ])
        print_table(headers, rows)
        print(f"    Pool Capacity: {cl_summary.get('rolling_capacity', '—')} | Max Depth: {cl_summary.get('context_depth', '200K')} | Reasoning: {cl_summary.get('thinking_budget', '64K')} | Opus Tier: {cl_summary.get('opus_tier', '—')}")
    else:
        print("    No Claude session keys configured in vault. Use Cookie Stacker to add sessionKey.")

    # 5. Gemini / Google DeepMind
    gm = data.get("gemini", {})
    gm_accounts = gm.get("accounts", [])
    gm_summary = gm.get("summary", {})
    print(f"\n[5] {gm.get('title', 'Google Gemini Engine Pool')} ({len(gm_accounts)} active engines)")
    if gm_accounts:
        headers = ["Engine / Session", "Tier / Mode", "Context Window", "Thinking / CoT", "Multimodal Ingestion", "Daily Quota", "Status"]
        rows = []
        for a in gm_accounts:
            rows.append([
                a.get("identifier", "—"),
                a.get("tier", "Universal High-Speed"),
                str(a.get("context_window", "1,000,000 tokens")),
                str(a.get("thinking_mode", "Dynamic CoT")),
                str(a.get("multimodal", "Vision + Docs")),
                str(a.get("daily_quota", "Unlimited")),
                a.get("status", "Active"),
            ])
        print_table(headers, rows)
        print(f"    Engine Architecture: {gm_summary.get('engine_architecture', 'Universal Web2API')} | Context Depth: {gm_summary.get('max_context', '1M')} | Thinking: {gm_summary.get('thinking_budget', 'Dynamic CoT')} | Image Gen: {gm_summary.get('image_gen', 'Imagen 3')}")
    else:
        print("    No Gemini engines loaded.")

    # 6. GLM / Zhipu AI
    glm_obj = data.get("glm", {})
    glm_accounts = glm_obj.get("accounts", [])
    glm_summary = glm_obj.get("summary", {})
    print(f"\n[6] {glm_obj.get('title', 'GLM / Zhipu AI Pool')} ({len(glm_accounts)} active engines)")
    if glm_accounts:
        headers = ["Account / Engine UID", "Mode / Tier", "Context Window", "Reasoning / CoT", "Web Grounding", "Concurrency", "Status"]
        rows = []
        for a in glm_accounts:
            rows.append([
                a.get("identifier", "—"),
                a.get("tier", "Self-Healing Guest Pool"),
                str(a.get("context_window", "128,000 tokens")),
                str(a.get("reasoning", "GLM-Zero CoT")),
                str(a.get("web_search", "Real-Time Search")),
                str(a.get("concurrency", "50 Slots")),
                a.get("status", "Active"),
            ])
        print_table(headers, rows)
        print(f"    Fleet Status: {glm_summary.get('pool_status', '—')} | Concurrency: {glm_summary.get('concurrency_slots', '50 Slots')} | Web Grounding: {glm_summary.get('web_grounding', 'Active')} | Auto-Heal: {glm_summary.get('auto_healing', 'Active')}")
    else:
        print("    No GLM engines configured.")
    print()


def cmd_accounts(args):
    """List or inspect stacked accounts in SQLite vault."""
    db.init_db()
    provider = args.provider.lower() if args.provider else None
    accounts = db.get_accounts(provider)

    if args.json:
        # Mask sensitive tokens
        sanitized = []
        for a in accounts:
            cp = dict(a)
            token = cp.get("token", "")
            if len(token) > 16:
                cp["token"] = token[:8] + "..." + token[-6:]
            sanitized.append(cp)
        print(json.dumps(sanitized, indent=2))
        return

    title = f"CREDENTIAL VAULT ({provider.upper() if provider else 'ALL PROVIDERS'})"
    print_header(title)
    if not accounts:
        print("  No accounts found in vault.")
        return

    headers = ["ID", "Provider", "Name / Email", "Plan", "Status", "Token (Masked)"]
    rows = []
    for a in accounts:
        token = a.get("token", "")
        masked = token[:6] + "..." + token[-4:] if len(token) > 12 else "****"
        rows.append([
            str(a["id"]),
            a["provider"].upper(),
            a.get("name") or a.get("identifier") or "—",
            (a.get("plan") or "free").upper(),
            a.get("status", "active"),
            masked,
        ])
    print_table(headers, rows)
    print()


def cmd_import(args):
    """Import accounts from JSON dump or file path."""
    source = args.source
    content = ""
    if Path(source).exists():
        content = Path(source).read_text(encoding="utf-8")
    else:
        content = source

    try:
        data = json.loads(content)
    except Exception as e:
        print(f"[-] Error: Could not parse JSON input: {e}")
        sys.exit(1)

    res = db.import_all_json(data)
    print(f"[+] {res.get('message', 'Import completed successfully!')}")


def cmd_export(args):
    """Export all accounts to a JSON file or stdout."""
    data = db.export_all_json()
    formatted = json.dumps(data, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(formatted, encoding="utf-8")
        print(f"[+] Successfully exported {data['total_accounts']} accounts to {out_path}")
    else:
        print(formatted)


def cmd_simulate(args):
    """View or toggle Device Simulation Mode."""
    db.init_db()
    action = (args.action or "status").lower()
    if action in ("on", "enable", "1", "true"):
        db.set_setting("simulation_mode", "1")
        print("[+] Device Simulation Mode ENABLED.")
        print("    Singularity will now simulate all models and providers cleanly without requiring local daemons.")
    elif action in ("off", "disable", "0", "false"):
        db.set_setting("simulation_mode", "0")
        print("[+] Device Simulation Mode DISABLED. Connecting to real provider daemons.")
    else:
        sim = providers.is_simulation_active()
        print(f"[*] Device Simulation Mode: {'ENABLED' if sim else 'DISABLED'}")
        print("    Usage: ./singular simulate [on|off]")


def cmd_host(args):
    """View or set remote provider cluster host."""
    db.init_db()
    if args.target:
        db.set_setting("remote_host", args.target)
        print(f"[+] Remote provider cluster host set to: {args.target}")
    else:
        current = db.get_setting("remote_host", "127.0.0.1")
        print(f"[*] Current provider cluster host: {current}")
        print("    Usage: ./singular host <ip_or_domain> (e.g. 192.168.1.100)")


def cmd_chat(args):
    """Execute a quick test completion through the local gateway."""
    import httpx

    model = args.model or "gpt-5-6-mini"
    prompt = args.prompt
    url = f"http://127.0.0.1:{args.port}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": args.stream,
    }
    if args.simulate:
        payload["simulate"] = True

    print(f"[*] Routing to Singularity Gateway ({model})...\n")

    if args.stream:
        try:
            with httpx.stream("POST", url, json=payload, timeout=60.0) as resp:
                if resp.status_code != 200:
                    print(f"[-] HTTP {resp.status_code}: {resp.read().decode('utf-8')}")
                    return
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            sys.stdout.write(delta)
                            sys.stdout.flush()
                        except Exception:
                            pass
                print()
        except httpx.ConnectError:
            print(f"[-] Could not connect to Singularity gateway at {url}.")
            print("    Start it first with: ./start.sh")
    else:
        try:
            resp = httpx.post(url, json=payload, timeout=60.0)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(content)
            else:
                print(f"[-] HTTP {resp.status_code}: {resp.text}")
        except httpx.ConnectError:
            print(f"[-] Could not connect to Singularity gateway at {url}.")
            print("    Start it first with: ./start.sh")


def cmd_service(args):
    """Start, stop, or restart provider services."""
    action = args.action.lower()
    pid = args.provider.lower() if args.provider else None
    if pid in ("all", "*", "fleet"):
        pid = None

    # If Singularity Gateway is running on port 9000, dispatch through it so workers run in-process
    gateway_online = False
    try:
        import httpx
        check = httpx.get("http://127.0.0.1:9000/healthz", timeout=1.0)
        if check.status_code == 200:
            gateway_online = True
    except Exception:
        gateway_online = False

    if gateway_online:
        import httpx
        try:
            if action == "start":
                url = f"http://127.0.0.1:9000/api/services/{pid}/start" if pid else "http://127.0.0.1:9000/api/services/start_all"
                resp = httpx.post(url, timeout=10.0)
                data = resp.json()
                if pid:
                    print(f"[{data.get('status')}] {data.get('message')}")
                else:
                    print("[+] Started all services via Gateway backend:")
                    for p, r in data.get("results", {}).items():
                        print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
                return
            elif action == "stop":
                url = f"http://127.0.0.1:9000/api/services/{pid}/stop" if pid else "http://127.0.0.1:9000/api/services/stop_all"
                resp = httpx.post(url, timeout=10.0)
                data = resp.json()
                if pid:
                    print(f"[{data.get('status')}] {data.get('message')}")
                else:
                    print("[+] Stopped all services via Gateway backend:")
                    for p, r in data.get("results", {}).items():
                        print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
                return
            elif action == "restart":
                if pid:
                    resp = httpx.post(f"http://127.0.0.1:9000/api/services/{pid}/restart", timeout=10.0)
                    data = resp.json()
                    print(f"[{data.get('status')}] {data.get('message')}")
                else:
                    httpx.post("http://127.0.0.1:9000/api/services/stop_all", timeout=10.0)
                    time.sleep(1.0)
                    resp = httpx.post("http://127.0.0.1:9000/api/services/start_all", timeout=10.0)
                    data = resp.json()
                    print("[+] Restarted all services via Gateway backend:")
                    for p, r in data.get("results", {}).items():
                        print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
                return
        except Exception:
            pass

    # Gateway not running: direct provider start
    if action == "start":
        if pid:
            res = providers.start_provider(pid)
            print(f"[{res.get('status')}] {res.get('message')}")
        else:
            res = providers.start_all_services()
            print("[+] Started all services:")
            for p, r in res.get("results", {}).items():
                print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
    elif action == "stop":
        if pid:
            res = providers.stop_provider(pid)
            print(f"[{res.get('status')}] {res.get('message')}")
        else:
            res = providers.stop_all_services()
            print("[+] Stopped all services:")
            for p, r in res.get("results", {}).items():
                print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
    elif action == "restart":
        if pid:
            providers.stop_provider(pid)
            time.sleep(1.0)
            res = providers.start_provider(pid)
            print(f"[{res.get('status')}] {res.get('message')}")
        else:
            providers.stop_all_services()
            time.sleep(1.0)
            res = providers.start_all_services()
            print("[+] Restarted all services:")
            for p, r in res.get("results", {}).items():
                print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")


# ==============================================================================
# Main Dispatcher
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="singular",
        description="Singularity Unified AI Gateway & Device Management CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # status
    p_status = subparsers.add_parser("status", help="Inspect gateway, providers, and accounts")
    p_status.add_argument("--json", action="store_true", help="Output compact JSON")

    # limits
    p_limits = subparsers.add_parser("limits", help="Inspect quotas and rate limits across providers")
    p_limits.add_argument("--json", action="store_true", help="Output compact JSON")

    # accounts
    p_accounts = subparsers.add_parser("accounts", help="List stacked accounts in SQLite vault")
    p_accounts.add_argument("provider", nargs="?", default=None, help="Filter by provider (chatgpt, claude, etc.)")
    p_accounts.add_argument("--json", action="store_true", help="Output JSON with masked tokens")

    # import
    p_import = subparsers.add_parser("import", help="Import accounts from JSON dump or file")
    p_import.add_argument("source", help="Path to JSON file or raw JSON string")

    # export
    p_export = subparsers.add_parser("export", help="Export account vault to JSON")
    p_export.add_argument("output", nargs="?", default=None, help="Output file path (default: stdout)")

    # simulate
    p_sim = subparsers.add_parser("simulate", help="Toggle device simulation mode")
    p_sim.add_argument("action", nargs="?", choices=["on", "off", "status"], default="status")

    # host
    p_host = subparsers.add_parser("host", help="View or set remote provider cluster host")
    p_host.add_argument("target", nargs="?", default=None, help="Remote host IP or hostname")

    # chat
    p_chat = subparsers.add_parser("chat", help="Send a test chat completion to Singularity")
    p_chat.add_argument("prompt", help="Prompt text to test")
    p_chat.add_argument("-m", "--model", default="gpt-5-6-mini", help="Model name (default: gpt-5-6-mini)")
    p_chat.add_argument("--stream", action="store_true", default=True, help="Stream response via SSE")
    p_chat.add_argument("--no-stream", dest="stream", action="store_false")
    p_chat.add_argument("--simulate", action="store_true", help="Force simulated response")
    p_chat.add_argument("-p", "--port", type=int, default=9000, help="Gateway port (default: 9000)")

    # service
    p_svc = subparsers.add_parser("service", help="Control provider daemons")
    p_svc.add_argument("action", choices=["start", "stop", "restart", "status"])
    p_svc.add_argument("provider", nargs="?", default=None, help="Provider ID (chatgpt, claude, etc.)")

    args = parser.parse_args()

    if not args.subcommand or args.subcommand == "status":
        cmd_status(args if args.subcommand else argparse.Namespace(json=False))
    elif args.subcommand == "limits":
        cmd_limits(args)
    elif args.subcommand == "accounts":
        cmd_accounts(args)
    elif args.subcommand == "import":
        cmd_import(args)
    elif args.subcommand == "export":
        cmd_export(args)
    elif args.subcommand == "simulate":
        cmd_simulate(args)
    elif args.subcommand == "host":
        cmd_host(args)
    elif args.subcommand == "chat":
        cmd_chat(args)
    elif args.subcommand == "service":
        cmd_service(args)


if __name__ == "__main__":
    main()
