#!/usr/bin/env python3
"""Sync xueqiu.com cookies from local Chromium browsers to GitHub Secret."""

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
            password = password or read_keychain_password(browser.keychain_services)
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


def set_github_secret(secret: str, value: str, repo: str | None) -> None:
    cmd = ["gh", "secret", "set", secret]
    if repo:
        cmd.extend(["-R", repo])
    subprocess.run(cmd, input=value, text=True, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local xueqiu.com browser cookies to GitHub Actions Secret")
    parser.add_argument("--domain", default="xueqiu.com")
    parser.add_argument("--secret", default="XUEQIU_COOKIE")
    parser.add_argument("--repo", help="GitHub repo, e.g. quadraticrain/stock-detect. Defaults to current gh repo.")
    parser.add_argument("--dry-run", action="store_true", help="Read cookies but do not update GitHub Secret")
    args = parser.parse_args()

    assert args.domain == "xueqiu.com", "This script is for xueqiu.com only"

    source, header = best_cookie_header(args.domain)
    if args.dry_run:
        print(f"Found {args.domain} cookies from {source}; cookie_count={header.count(';') + 1}")
        return 0

    set_github_secret(args.secret, header, args.repo)
    print(f"Updated GitHub Secret {args.secret} from {source}; cookie_count={header.count(';') + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
