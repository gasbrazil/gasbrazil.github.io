#!/usr/bin/env python3
"""
Builds the GasBrazil Admin Panel (/admin/index.html).

Provides a secure, browser-based management portal to:
  - View live passcode protection status & scope
  - Update site passcode with real-time SHA-256 computation
  - Toggle protection on/off and switch between Total Stealth and Dashboards-only
  - Publish changes directly to GitHub via Personal Access Token (PAT)
  - Download updated config/auth.json or copy CLI commands
  - Test passcodes locally and trigger immediate site lock
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))
import dashboard_kit as kit  # noqa: E402

ADMIN_DIR = ROOT / "admin"
ADMIN_HTML = ADMIN_DIR / "index.html"


def build_admin_html() -> str:
    auth_cfg = kit.get_auth_config()

    page_head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin Panel — GasBrazil</title>
<meta name="robots" content="noindex, nofollow">
{kit.brand_head_html(social=False)}
<script>{kit.JS_BOOT}</script>
<style>
{kit.THEME_CSS}
{kit.TYPO_WEIGHT_CSS}
/* Specific Admin UI Enhancements */
.admin-badge-row {{
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}}
.admin-grid-2 {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}}
@media (max-width: 680px) {{
  .admin-grid-2 {{
    grid-template-columns: 1fr;
  }}
}}
.admin-radio-group {{
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 6px;
}}
.admin-radio-label {{
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  transition: all 0.18s ease;
}}
.admin-radio-label:hover {{
  border-color: var(--accent);
  background: var(--panel-hover);
}}
.admin-radio-label input[type="radio"] {{
  margin-top: 3px;
}}
.admin-radio-desc {{
  font-size: 11.5px;
  color: var(--muted);
  margin-top: 2px;
}}
.admin-switch-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}}
.admin-switch-label {{
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}}
.admin-switch-sub {{
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}}
.admin-alert {{
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  margin-bottom: 14px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}}
.admin-alert.info {{
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
  color: var(--text);
}}
.admin-alert.success {{
  background: color-mix(in srgb, #10b981 12%, transparent);
  border: 1px solid color-mix(in srgb, #10b981 30%, transparent);
  color: #10b981;
}}
.admin-alert.error {{
  background: color-mix(in srgb, #ef4444 12%, transparent);
  border: 1px solid color-mix(in srgb, #ef4444 30%, transparent);
  color: #ef4444;
}}
.admin-hash-box {{
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--accent);
  word-break: break-all;
}}
</style>
</head>
"""

    brand_menu = kit.products_dropdown_html(
        "admin",
        '<a class="masthead-brand" id="link-home" href="../" data-i18n="navHome">GasBrazil</a>',
    )

    masthead = f"""<header class="dash-head">
  <div class="masthead">
    <div class="masthead-ident">
      {brand_menu}
      <span class="crumb-sep" aria-hidden="true"></span>
      <h1 class="page-title">Admin Panel</h1>
    </div>
    <div class="nav-trail">
      <a class="navlink" href="../wiki/" data-i18n="navWiki">Wiki</a>
      <a class="navlink" href="../about/" data-i18n="navAbout">About</a>
      <button type="button" class="gb-search-btn" id="gb-search-trigger" aria-label="Search (Ctrl+K)" title="Search (Ctrl+K)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <span data-i18n="searchBtn">Search</span> <kbd>Ctrl+K</kbd>
      </button>
      <button type="button" class="auth-lock-btn" id="gb-auth-lock" aria-label="Lock site" title="Lock site" data-i18n-title="authLockBtn">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        <span data-i18n="authLockBtn">Lock</span>
      </button>
    </div>
    <button type="button" id="lang-toggle" class="langBtn" aria-label="Português">PT</button>
    <button id="theme-toggle" title="Toggle theme" aria-label="Toggle theme"></button>
  </div>
  {kit._PRODUCTS_DROPDOWN_JS}
</header>"""

    body = f"""{page_head}
<body>
<a class="skip-link" href="#admin-main">Skip to main content</a>
{masthead}
<div class="flagbar" aria-hidden="true"></div>

<main class="admin-wrap" id="admin-main">
  <div style="margin-bottom: 24px;">
    <h2 style="font-size: 24px; font-weight: 600; margin: 0 0 6px;">Site Access &amp; Stealth Settings</h2>
    <p style="font-size: 13.5px; color: var(--muted); margin: 0;">Configure site passcode, stealth gating mode, and deploy changes directly to GitHub.</p>
  </div>

  <!-- Status Card -->
  <div class="admin-card">
    <div class="admin-card-head">
      <h3 class="admin-card-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        Current Protection Status
      </h3>
      <span id="badge-status" class="admin-status-badge {'active' if auth_cfg.get('enabled') else 'disabled'}">
        {'● Guard Active' if auth_cfg.get('enabled') else '○ Guard Disabled'}
      </span>
    </div>
    <div class="admin-grid-2">
      <div>
        <div class="admin-form-label">Scope</div>
        <div id="stat-scope" style="font-size: 13.5px; font-weight: 500; color: var(--text);">
          {'Total Stealth (All pages locked)' if auth_cfg.get('scope') == 'all' else 'Dashboards Only (Landing page public)'}
        </div>
      </div>
      <div>
        <div class="admin-form-label">Session Duration</div>
        <div id="stat-days" style="font-size: 13.5px; font-weight: 500; color: var(--text);">{auth_cfg.get('session_days', 30)} days</div>
      </div>
    </div>
    <div style="margin-top: 14px;">
      <div class="admin-form-label">Salt</div>
      <div class="admin-code">{auth_cfg.get('salt', 'gasbrazil-auth-salt-2026')}</div>
    </div>
    <div style="margin-top: 12px;">
      <div class="admin-form-label">Active SHA-256 Hash</div>
      <div class="admin-hash-box">{auth_cfg.get('hash', '')}</div>
    </div>
  </div>

  <!-- Configuration Form -->
  <div class="admin-card">
    <div class="admin-card-head">
      <h3 class="admin-card-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        Adjust Protection Settings
      </h3>
    </div>

    <!-- Toggle Protection -->
    <div class="admin-form-group">
      <div class="admin-switch-row">
        <div>
          <div class="admin-switch-label">Passcode Protection Guard</div>
          <div class="admin-switch-sub">When enabled, visitors must enter the correct passcode to access protected pages.</div>
        </div>
        <input type="checkbox" id="field-enabled" {'checked' if auth_cfg.get('enabled') else ''} style="width: 20px; height: 20px; cursor: pointer;">
      </div>
    </div>

    <!-- Scope Selection -->
    <div class="admin-form-group">
      <label class="admin-form-label">Protection Scope</label>
      <div class="admin-radio-group">
        <label class="admin-radio-label">
          <input type="radio" name="field-scope" value="all" {'checked' if auth_cfg.get('scope') == 'all' else ''}>
          <div>
            <strong>Total Stealth (Recommended)</strong>
            <div class="admin-radio-desc">Every page is locked behind the passcode screen, including the landing hub (/) and about page.</div>
          </div>
        </label>
        <label class="admin-radio-label">
          <input type="radio" name="field-scope" value="dashboards" {'checked' if auth_cfg.get('scope') == 'dashboards' else ''}>
          <div>
            <strong>Dashboards Only</strong>
            <div class="admin-radio-desc">The landing hub (/) is public; individual dashboard pages (/desk/, /ons/, /poc/, etc.) require the passcode.</div>
          </div>
        </label>
      </div>
    </div>

    <!-- Change Passcode -->
    <div class="admin-form-group">
      <label class="admin-form-label" for="field-password">New Passcode (Leave blank to keep existing)</label>
      <div style="position: relative;">
        <input type="password" id="field-password" class="admin-input" placeholder="Enter new passcode…" autocomplete="new-password">
        <button type="button" id="btn-toggle-eye" class="gb-auth-eye-btn" style="right: 8px; top: 7px;" aria-label="Toggle password view">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
      </div>
      <div class="admin-form-help">Passwords are never stored in plaintext. They are salted and hashed with SHA-256.</div>
    </div>

    <!-- Live Hash Preview -->
    <div class="admin-form-group" id="wrap-new-hash" style="display: none;">
      <label class="admin-form-label">Computed SHA-256 Hash Preview</label>
      <div id="preview-new-hash" class="admin-hash-box"></div>
    </div>

    <!-- Session Duration -->
    <div class="admin-form-group">
      <label class="admin-form-label" for="field-days">Session Expiration (Days)</label>
      <input type="number" id="field-days" class="admin-input" value="{auth_cfg.get('session_days', 30)}" min="1" max="365" style="max-width: 140px;">
      <div class="admin-form-help">How many days an unlocked browser session remains valid before requiring re-entry.</div>
    </div>
  </div>

  <!-- Direct GitHub Sync Card -->
  <div class="admin-card">
    <div class="admin-card-head">
      <h3 class="admin-card-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
        1-Click Publish to Live Site (GitHub Sync)
      </h3>
    </div>
    <div class="admin-alert info">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex: none; margin-top: 1px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      <div>
        Because GasBrazil is hosted on GitHub Pages, publishing updates commits <code>config/auth.json</code> to your repository. GitHub Actions will automatically rebuild and deploy the live site within ~1-2 minutes.
      </div>
    </div>

    <div class="admin-form-group">
      <label class="admin-form-label" for="field-pat">GitHub Personal Access Token (PAT)</label>
      <input type="password" id="field-pat" class="admin-input" placeholder="ghp_... or github_pat_..." autocomplete="off">
      <div class="admin-form-help">Needs repository <code>contents:write</code> permission. Stored only in your local browser storage if remembered.</div>
    </div>

    <div class="admin-form-group" style="display: flex; align-items: center; gap: 8px;">
      <input type="checkbox" id="field-remember-pat" checked style="cursor: pointer;">
      <label for="field-remember-pat" style="font-size: 12.5px; color: var(--muted); cursor: pointer;">Remember token in this browser (stored in localStorage only)</label>
    </div>

    <div id="publish-status-box" style="margin-top: 12px; display: none;"></div>

    <div style="margin-top: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
      <button type="button" id="btn-publish-github" class="admin-btn admin-btn-primary">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        Publish Changes to GitHub
      </button>
      <button type="button" id="btn-download-json" class="admin-btn admin-btn-secondary">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        Download auth.json
      </button>
    </div>
  </div>

  <!-- CLI & Offline Instructions -->
  <div class="admin-card">
    <div class="admin-card-head">
      <h3 class="admin-card-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
        CLI &amp; Offline Management
      </h3>
    </div>
    <p style="font-size: 13px; color: var(--muted); margin: 0 0 12px;">You can also configure security settings directly from the terminal using the repo helper script:</p>
    <div class="admin-code" style="padding: 10px 14px; font-size: 12.5px; display: block; overflow-x: auto; white-space: pre;">python manage_auth.py --password "your-new-passcode" --scope all --enable</div>
  </div>

  <!-- Session Diagnostics -->
  <div class="admin-card">
    <div class="admin-card-head">
      <h3 class="admin-card-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        Session Diagnostics &amp; Immediate Lock
      </h3>
    </div>
    <p style="font-size: 13px; color: var(--muted); margin: 0 0 14px;">Test entering a passcode against the live config, or immediately lock this browser session to test the login screen.</p>
    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
      <button type="button" id="btn-lock-now" class="admin-btn admin-btn-secondary" style="color: #ef4444; border-color: color-mix(in srgb, #ef4444 30%, transparent);">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        Lock Site Now (Test Lock Screen)
      </button>
      <button type="button" id="btn-clear-session" class="admin-btn admin-btn-secondary">
        Reset Stored Session
      </button>
    </div>
  </div>
</main>

<footer class="site">
  &copy; <span id="year"></span> GasBrazil &middot; <a href="../">Home</a> &middot; <a href="../wiki/">Wiki</a> &middot; <a href="../about/">About</a>
</footer>

<script>
{kit.JS_DECODE}
{kit.JS_THEME_TOGGLE}
{kit.JS_I18N}
document.getElementById("year").textContent = new Date().getFullYear();
initThemeToggle("theme-toggle");
initLangToggle("lang-toggle");

(function() {{
  const CURRENT_SALT = {json.dumps(auth_cfg.get("salt", "gasbrazil-auth-salt-2026"))};
  let currentComputedHash = {json.dumps(auth_cfg.get("hash", ""))};

  // Restore saved PAT if available
  const savedPat = localStorage.getItem("gb_admin_pat");
  if (savedPat) {{
    const patField = document.getElementById("field-pat");
    if (patField) patField.value = savedPat;
  }}

  // Eye toggle on password
  const eyeBtn = document.getElementById("btn-toggle-eye");
  const passField = document.getElementById("field-password");
  if (eyeBtn && passField) {{
    eyeBtn.addEventListener("click", () => {{
      const isPass = passField.type === "password";
      passField.type = isPass ? "text" : "password";
      eyeBtn.innerHTML = isPass
        ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    }});
  }}

  // Live SHA-256 calculation
  const wrapHash = document.getElementById("wrap-new-hash");
  const previewHash = document.getElementById("preview-new-hash");
  if (passField) {{
    passField.addEventListener("input", async () => {{
      const val = passField.value.trim();
      if (!val) {{
        wrapHash.style.display = "none";
        currentComputedHash = {json.dumps(auth_cfg.get("hash", ""))};
        return;
      }}
      try {{
        const h = await gbSha256(val + ":" + CURRENT_SALT);
        currentComputedHash = h;
        previewHash.textContent = h;
        wrapHash.style.display = "block";
      }} catch (err) {{
        console.error(err);
      }}
    }});
  }}

  // Build target config object
  function getDesiredConfig() {{
    const enabled = document.getElementById("field-enabled").checked;
    const scopeRadio = document.querySelector('input[name="field-scope"]:checked');
    const scope = scopeRadio ? scopeRadio.value : "all";
    const days = parseInt(document.getElementById("field-days").value, 10) || 30;
    return {{
      enabled: enabled,
      scope: scope,
      salt: CURRENT_SALT,
      hash: currentComputedHash,
      session_days: days
    }};
  }}

  // Download JSON
  const downloadBtn = document.getElementById("btn-download-json");
  if (downloadBtn) {{
    downloadBtn.addEventListener("click", () => {{
      const cfg = getDesiredConfig();
      const text = JSON.stringify(cfg, null, 2) + "\\n";
      const blob = new Blob([text], {{ type: "application/json" }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "auth.json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      gbShowToast("Downloaded config/auth.json");
    }});
  }}

  // Lock site now
  const lockBtn = document.getElementById("btn-lock-now");
  if (lockBtn) {{
    lockBtn.addEventListener("click", () => {{
      gbLockSite();
    }});
  }}

  // Clear session
  const clearBtn = document.getElementById("btn-clear-session");
  if (clearBtn) {{
    clearBtn.addEventListener("click", () => {{
      localStorage.removeItem("gasbrazil-auth-v1");
      gbShowToast("Local session cleared");
    }});
  }}

  // Publish to GitHub via Contents API
  const publishBtn = document.getElementById("btn-publish-github");
  const statusBox = document.getElementById("publish-status-box");
  if (publishBtn) {{
    publishBtn.addEventListener("click", async () => {{
      const patField = document.getElementById("field-pat");
      const pat = (patField ? patField.value : "").trim();
      if (!pat) {{
        statusBox.className = "admin-alert error";
        statusBox.innerHTML = "<strong>Error:</strong> Please provide a GitHub Personal Access Token (PAT) with repo contents write permission.";
        statusBox.style.display = "block";
        if (patField) patField.focus();
        return;
      }}

      const rememberCheck = document.getElementById("field-remember-pat");
      if (rememberCheck && rememberCheck.checked) {{
        localStorage.setItem("gb_admin_pat", pat);
      }} else {{
        localStorage.removeItem("gb_admin_pat");
      }}

      publishBtn.disabled = true;
      publishBtn.textContent = "Publishing to GitHub…";
      statusBox.className = "admin-alert info";
      statusBox.innerHTML = "Connecting to GitHub API to update config/auth.json…";
      statusBox.style.display = "block";

      const repo = "gasbrazil/gasbrazil.github.io";
      const filePath = "config/auth.json";
      const apiUrl = "https://api.github.com/repos/" + repo + "/contents/" + filePath;

      try {{
        // 1. Get current file SHA
        const getRes = await fetch(apiUrl, {{
          headers: {{
            "Authorization": "Bearer " + pat,
            "Accept": "application/vnd.github.v3+json"
          }}
        }});

        if (!getRes.ok && getRes.status !== 404) {{
          throw new Error("GitHub API Error " + getRes.status + ": " + (await getRes.text()));
        }}

        let currentSha = null;
        if (getRes.ok) {{
          const getData = await getRes.json();
          currentSha = getData.sha;
        }}

        // 2. Put updated auth.json
        const newCfg = getDesiredConfig();
        const contentStr = JSON.stringify(newCfg, null, 2) + "\\n";
        const contentB64 = btoa(unescape(encodeURIComponent(contentStr)));

        const putBody = {{
          message: "chore(auth): update site passcode & security settings from admin panel",
          content: contentB64
        }};
        if (currentSha) putBody.sha = currentSha;

        const putRes = await fetch(apiUrl, {{
          method: "PUT",
          headers: {{
            "Authorization": "Bearer " + pat,
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
          }},
          body: JSON.stringify(putBody)
        }});

        if (!putRes.ok) {{
          const errData = await putRes.json().catch(() => ({{}}));
          throw new Error(errData.message || ("GitHub API Error " + putRes.status));
        }}

        statusBox.className = "admin-alert success";
        statusBox.innerHTML = "<strong>Success!</strong> Successfully updated <code>config/auth.json</code> on GitHub. GitHub Actions is now rebuilding and publishing the live site (~1 minute).";
        gbShowToast("Changes published to GitHub!");

        // Update local session with new hash so admin doesn't get locked out
        if (newCfg.hash) {{
          gbSaveSession(newCfg.hash, newCfg.session_days);
        }}
      }} catch (err) {{
        console.error(err);
        statusBox.className = "admin-alert error";
        statusBox.innerHTML = "<strong>Publish Failed:</strong> " + escapeHtml(err.message || String(err));
      }} finally {{
        publishBtn.disabled = false;
        publishBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg> Publish Changes to GitHub';
      }}
    }});
  }}
}})();
</script>
</body>
</html>
"""
    return body


def write_admin(out_path: Path | None = None) -> Path:
    out_path = out_path or ADMIN_HTML
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = build_admin_html()
    out_path.write_text(html_content, encoding="utf-8")
    print(f"Wrote admin page ({len(html_content):,} bytes) to {out_path}")
    return out_path


if __name__ == "__main__":
    write_admin()
