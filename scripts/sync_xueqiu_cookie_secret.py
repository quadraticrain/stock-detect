#!/usr/bin/env python3
"""Read xueqiu.com cookies from local Chromium browsers.

Default action: refresh the project `.env` `XUEQIU_COOKIE` (local fetch flow).
`--dry-run` reads cookies and prints a summary without writing anything.

Chrome cookie decryption needs the browser's "Safe Storage" key. Resolution order:
1. env `CHROME_SAFE_STORAGE_PASSWORD`
2. state file `.workbuddy/state/chrome_safe_storage`
3. macOS keychain (`security find-generic-password -w -s "Chrome Safe Storage"`)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".workbuddy" / "state"
STORAGE_PASSWORD_FILE = STATE_DIR / "chrome_safe_storage"
STORAGE_PASSWORD_ENV = "CHROME_SAFE_STORAGE_PASSWORD"


@dataclass(frozen=True)
class Browser:
    name: str
    data_dir: Path
    keychain_services: tuple[str, ...]


@dataclass(frozen=True)
class BrowserCookie:
    name: str
    value: str
    expires_utc: int


MAC_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
AUTH_COOKIE_NAMES = {"xq_a_token", "xqat", "xq_id_token", "xq_r_token"}


def browser_candidates() -> list[Browser]:
    home = Path.home()
    app_support = home / "Library" / "Application Support"
    return [
        Browser("Chrome", app_support / "Google" / "Chrome", ("Chrome Safe Storage",)),
        Browser("Arc", app_support / "Arc" / "User Data", ("Arc Safe Storage", "Chrome Safe Storage")),
        Browser("Edge", app_support / "Microsoft Edge", ("Microsoft Edge Safe Storage",)),
        Browser("Brave", app_support / "BraveSoftware" / "Brave-Browser", ("Brave Safe Storage",)),
        Browser("Chromium", app_support / "Chromium", ("Chromium Safe Storage",)),
    ]


def find_cookie_dbs(browser: Browser) -> list[Path]:
    if not browser.data_dir.exists():
        return []
    return sorted(browser.data_dir.glob("*/Network/Cookies")) + sorted(browser.data_dir.glob("*/Cookies"))


def chrome_expires_at(expires_utc: int) -> datetime | None:
    if not expires_utc:
        return None
    return MAC_EPOCH + timedelta(microseconds=expires_utc)


def is_expired(expires_utc: int, *, now: datetime | None = None) -> bool:
    expires_at = chrome_expires_at(expires_utc)
    return bool(expires_at and expires_at <= (now or datetime.now(timezone.utc)))


def format_cookie_header(cookies: list[BrowserCookie]) -> str:
    fresh = [cookie for cookie in cookies if cookie.value and not is_expired(cookie.expires_utc)]
    fresh.sort(key=lambda cookie: (cookie.name not in AUTH_COOKIE_NAMES, cookie.name))
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in fresh)


def read_keychain_password(services: tuple[str, ...]) -> str | None:
    for service in services:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", service],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.rstrip("\n")
    return None


def resolve_storage_password(browser: Browser) -> str | None:
    """Resolve the browser Safe Storage key: env → state file → keychain."""
    password = os.environ.get(STORAGE_PASSWORD_ENV)
    if password:
        return password
    if STORAGE_PASSWORD_FILE.exists():
        password = STORAGE_PASSWORD_FILE.read_text().strip()
        if password:
            return password
    return read_keychain_password(browser.keychain_services)


def decrypt_chrome_cookie(encrypted_value: bytes, password: str, host_key: str) -> str:
    if not encrypted_value:
        return ""
    value = encrypted_value[3:] if encrypted_value.startswith((b"v10", b"v11")) else encrypted_value
    key = hashlib.pbkdf2_hmac("sha1", password.encode(), b"saltysalt", 1003, 16)
    result = subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-128-cbc",
            "-K",
            key.hex(),
            "-iv",
            (b" " * 16).hex(),
        ],
        input=value,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("openssl failed to decrypt browser cookie")
    plain = result.stdout
    host_hash = hashlib.sha256(host_key.encode()).digest()
    if plain.startswith(host_hash):
        plain = plain[len(host_hash) :]
    return plain.decode("utf-8", errors="replace")


def load_cookies(db_path: Path, browser: Browser, domain: str) -> list[BrowserCookie]:
    password: str | None = None
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "Cookies"
        shutil.copy2(db_path, tmp_db)
        conn = sqlite3.connect(tmp_db)
        try:
            rows = conn.execute(
                """
                SELECT host_key, name, value, encrypted_value, expires_utc
                FROM cookies
                WHERE host_key = ? OR host_key LIKE ?
                """,
                (domain, f"%.{domain}"),
            ).fetchall()
        finally:
            conn.close()

    cookies: list[BrowserCookie] = []
    for host_key, name, value, encrypted_value, expires_utc in rows:
        if not value and encrypted_value:
            password = password or resolve_storage_password(browser)
            if not password:
                continue
            value = decrypt_chrome_cookie(encrypted_value, password, host_key)
        cookies.append(BrowserCookie(name=name, value=value, expires_utc=int(expires_utc or 0)))
    return cookies


def best_cookie_header(domain: str) -> tuple[str, str]:
    best_source = ""
    best_header = ""
    best_score = -1
    for browser in browser_candidates():
        for db_path in find_cookie_dbs(browser):
            try:
                header = format_cookie_header(load_cookies(db_path, browser, domain))
            except Exception as exc:
                print(f"skip {browser.name} {db_path}: {exc}", file=sys.stderr)
                continue
            names = {part.split("=", 1)[0] for part in header.split("; ") if part}
            score = len(names & AUTH_COOKIE_NAMES) * 10 + len(names)
            if score > best_score:
                best_source = f"{browser.name}: {db_path.parent.parent.name}/{db_path.parent.name}"
                best_header = header
                best_score = score
    if not best_header or not ({part.split("=", 1)[0] for part in best_header.split("; ")} & AUTH_COOKIE_NAMES):
        raise RuntimeError(f"No logged-in {domain} cookies found. Open the browser and log in to Xueqiu first.")
    return best_source, best_header


def write_env_cookie(header: str) -> None:
    """Persist the fresh cookie header to project `.env` (XUEQIU_COOKIE line)."""
    env_path = ROOT / ".env"
    new_line = f"XUEQIU_COOKIE='{header}'"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        replaced = False
        for index, line in enumerate(lines):
            if line.startswith("XUEQIU_COOKIE="):
                lines[index] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)
        env_path.write_text("\n".join(lines) + "\n")
    else:
        env_path.write_text(new_line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read local xueqiu.com browser cookies and refresh .env")
    parser.add_argument("--domain", default="xueqiu.com")
    parser.add_argument("--dry-run", action="store_true", help="Read cookies but do not write anywhere")
    args = parser.parse_args()

    assert args.domain == "xueqiu.com", "This script is for xueqiu.com only"

    source, header = best_cookie_header(args.domain)
    if args.dry_run:
        print(f"Found {args.domain} cookies from {source}; cookie_count={header.count(';') + 1}")
        return 0

    write_env_cookie(header)
    print(f"Updated .env XUEQIU_COOKIE from {source}; cookie_count={header.count(';') + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
