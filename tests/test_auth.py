"""
Tests for GasBrazil Site Passcode Authentication & Stealth Access Guard.

Covers:
  - config/auth.json structure, validity, and default hash
  - manage_auth.py hashing logic and CLI operations
  - shared/dashboard_kit.py auth guard helpers, JS_BOOT, and JS_I18N
  - admin/admin.py generation, security headers, and controls
  - Integration across landing page, admin panel, robots.txt, and built shells
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT))
import dashboard_kit as kit  # noqa: E402

import manage_auth  # noqa: E402


def test_auth_config_file_exists_and_valid():
    cfg_path = ROOT / "config" / "auth.json"
    assert cfg_path.exists(), "config/auth.json must exist"

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert isinstance(cfg.get("enabled"), bool)
    assert cfg.get("scope") in ("all", "dashboards")
    assert isinstance(cfg.get("salt"), str) and len(cfg["salt"]) >= 8
    assert isinstance(cfg.get("hash"), str) and len(cfg["hash"]) == 64
    assert isinstance(cfg.get("session_days"), int) and cfg["session_days"] > 0


def test_auth_hash_matches_initial_password():
    salt = "gasbrazil-auth-salt-2026"
    pwd = "gas-brazil-2026"
    expected = hashlib.sha256(f"{pwd}:{salt}".encode()).hexdigest()
    assert expected == "e08faeb3ac5faffe44f959ee4ed05c404ba6e3681992051ba6090724e7f5d8ff"

    cfg = kit.get_auth_config()
    assert cfg["hash"] == expected
    assert cfg["salt"] == salt
    assert cfg["enabled"] is True
    assert cfg["scope"] == "all"


def test_manage_auth_compute_hash():
    salt = "custom-test-salt"
    pwd = "secret-passcode"
    h = manage_auth.compute_hash(pwd, salt)
    assert h == hashlib.sha256(f"{pwd}:{salt}".encode()).hexdigest()


def test_manage_auth_cli_status():
    res = subprocess.run(
        [sys.executable, str(ROOT / "manage_auth.py"), "--status"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "GasBrazil Authentication Status" in res.stdout
    assert "Status:" in res.stdout
    assert "Scope:" in res.stdout


def test_dashboard_kit_js_boot_contains_auth_lock():
    assert "gb-locked" in kit.JS_BOOT
    assert "gasbrazil-auth-v1" in kit.JS_BOOT
    assert "window._gbAuthConfig" in kit.JS_BOOT
    assert "requiresAuth" in kit.JS_BOOT


def test_dashboard_kit_js_i18n_contains_auth_guard():
    assert 'GB_AUTH_KEY = "gasbrazil-auth-v1"' in kit.JS_I18N
    assert "function gbSha256(" in kit.JS_I18N
    assert "function initAuthGuard(" in kit.JS_I18N
    assert "function showAuthModal(" in kit.JS_I18N
    assert "function gbLockSite(" in kit.JS_I18N
    assert "gb-auth-overlay" in kit.JS_I18N
    assert "gb-auth-card" in kit.JS_I18N
    assert "authTitle:" in kit.JS_I18N
    assert "authSubtitle:" in kit.JS_I18N
    assert "authPlaceholder:" in kit.JS_I18N
    assert "authSubmit:" in kit.JS_I18N
    assert "authError:" in kit.JS_I18N


def test_dashboard_kit_masthead_has_lock_button():
    masthead = kit.masthead_html("desk")
    assert 'id="gb-auth-lock"' in masthead
    assert "auth-lock-btn" in masthead
    assert "data-i18n-title=\"authLockBtn\"" in masthead


def test_admin_page_generation():
    sys.path.insert(0, str(ROOT / "admin"))
    import admin
    out_path = admin.write_admin()
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")

    assert '<meta name="robots" content="noindex, nofollow">' in content
    assert "Site Access &amp; Stealth Settings" in content
    assert "Current Protection Status" in content
    assert 'id="field-enabled"' in content
    assert 'name="field-scope"' in content
    assert 'id="field-password"' in content
    assert 'id="btn-publish-github"' in content
    assert 'id="btn-download-json"' in content
    assert 'id="btn-lock-now"' in content
    assert 'id="gb-auth-lock"' in content


def test_landing_page_and_robots():
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="gb-auth-lock"' in index_html
    assert "gb-locked" in index_html

    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    assert "Disallow: /admin/" in robots
