#!/usr/bin/env python3
"""
CLI helper for managing GasBrazil.com authentication and stealth gate.

Usage:
    python manage_auth.py --status
    python manage_auth.py --password "new-passcode"
    python manage_auth.py --enable
    python manage_auth.py --disable
    python manage_auth.py --scope all         # Total stealth (all pages)
    python manage_auth.py --scope dashboards  # Public showcase, gated dashboards
    python manage_auth.py --rebuild           # Rebuild home and resync dashboard shells
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "auth.json"

DEFAULT_SALT = "gasbrazil-auth-salt-2026"


def load_auth_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        default_cfg = {
            "enabled": True,
            "scope": "all",
            "salt": DEFAULT_SALT,
            "hash": hash_passcode("gas-brazil-2026", DEFAULT_SALT),
            "session_days": 30,
            "updated_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        save_auth_config(default_cfg)
        return default_cfg
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False, "scope": "all", "salt": DEFAULT_SALT, "hash": "", "session_days": 30}


def save_auth_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg["updated_at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def hash_passcode(passcode: str, salt: str = DEFAULT_SALT) -> str:
    raw = f"{passcode}:{salt}".encode()
    return hashlib.sha256(raw).hexdigest()


compute_hash = hash_passcode


def rebuild_site() -> None:
    print("Rebuilding home, admin, and resyncing dashboard shells...")
    res1 = subprocess.run([sys.executable, str(ROOT / "build_home.py")], check=True)
    res2 = subprocess.run([sys.executable, str(ROOT / "shared" / "resync_built_shells.py")], check=True)
    if res1.returncode == 0 and res2.returncode == 0:
        print("Site shells successfully rebuilt.")


def print_status() -> None:
    cfg = load_auth_config()
    status_str = "ENABLED (Gated)" if cfg.get("enabled") else "DISABLED (Open)"
    scope_str = "All pages (Total Stealth)" if cfg.get("scope") == "all" else "Dashboards only (Public Showcase)"
    print("\n=== GasBrazil Authentication Status ===")
    print(f"Status:       {status_str}")
    print(f"Scope:        {scope_str}")
    print(f"Session:      {cfg.get('session_days', 30)} days")
    print(f"Salt:         {cfg.get('salt', DEFAULT_SALT)}")
    print(f"Hash:         {cfg.get('hash', 'none')[:16]}...")
    print(f"Last Updated: {cfg.get('updated_at', 'unknown')}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage GasBrazil site authentication.")
    parser.add_argument("--status", action="store_true", help="Show current authentication configuration.")
    parser.add_argument("--password", type=str, help="Set a new site passcode.")
    parser.add_argument("--enable", action="store_true", help="Enable the authentication login screen.")
    parser.add_argument("--disable", action="store_true", help="Disable the authentication login screen.")
    parser.add_argument("--scope", choices=["all", "dashboards"], help="Set gating scope: all (stealth) or dashboards (public showcase).")
    parser.add_argument("--session-days", type=int, help="Number of days before session expires (default: 30).")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild all HTML shells after updating config.")
    parser.add_argument("--no-rebuild", action="store_true", help="Do not trigger shell rebuild.")

    args = parser.parse_args()

    if len(sys.argv) == 1 or args.status:
        print_status()
        return

    cfg = load_auth_config()
    changed = False

    if args.enable:
        cfg["enabled"] = True
        changed = True
        print("Set: Authentication ENABLED")

    if args.disable:
        cfg["enabled"] = False
        changed = True
        print("Set: Authentication DISABLED")

    if args.scope:
        cfg["scope"] = args.scope
        changed = True
        print(f"Set: Scope = {args.scope}")

    if args.session_days:
        cfg["session_days"] = args.session_days
        changed = True
        print(f"Set: Session days = {args.session_days}")

    if args.password:
        salt = cfg.get("salt") or DEFAULT_SALT
        new_hash = hash_passcode(args.password, salt)
        cfg["hash"] = new_hash
        cfg["salt"] = salt
        changed = True
        print(f"Set: Passcode updated. New hash: {new_hash[:16]}...")

    if changed:
        save_auth_config(cfg)
        print("Saved updated configuration to config/auth.json.")
        print_status()
        if not args.no_rebuild:
            rebuild_site()
    elif args.rebuild:
        rebuild_site()


if __name__ == "__main__":
    main()
