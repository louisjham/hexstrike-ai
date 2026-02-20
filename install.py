#!/usr/bin/env python3
"""
HexClaw install.py
==================
Bootstraps everything needed to run the HexClaw autonomous agent:
  1. Python pip dependencies (litellm, redis, telegram, duckdb, msgraph, google-api)
  2. .env configuration (Telegram, AI keys, Email/App passwords)
  3. Database setup (PostgreSQL + Redis)
  4. System service registration (systemd/Windows)
"""

import os
import sys
import shutil
import platform
import subprocess
import argparse
import textwrap
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
ENV_FILE = ROOT / ".env"
REQUIREMENTS = [
    "litellm",
    "redis",
    "python-telegram-bot",
    "temp-mails",
    "psycopg2-binary",
    "duckdb",
    "msgraph-sdk",
    "google-api-python-client",
    "python-dotenv",
    "pyyaml"
]

BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"

def ok(msg): print(f"  {GREEN}[+]{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}[?]{RESET}  {msg}")
def err(msg): print(f"  {RED}[X]{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{CYAN}== {msg} =={RESET}")

# ── Steps ─────────────────────────────────────────────────────────────────────

def install_deps():
    header("Step 1: Install Dependencies")
    print(f"Installing: {', '.join(REQUIREMENTS)}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade"] + REQUIREMENTS)
        ok("All dependencies installed.")
    except Exception as e:
        err(f"Dependency install failed: {e}")

def setup_env():
    header("Step 2: .env Configuration")
    if ENV_FILE.exists():
        warn(".env already exists. Skipping overwrite.")
        return

    config = {
        "TELEGRAM_BOT_TOKEN": input(f"    {BOLD}TELEGRAM_BOT_TOKEN{RESET}: "),
        "TELEGRAM_CHAT_ID": input(f"    {BOLD}TELEGRAM_CHAT_ID{RESET}: "),
        "GOOGLE_API_KEY": input(f"    {BOLD}GOOGLE_API_KEY (Gemini){RESET}: "),
        "APP_EMAIL": input(f"    {BOLD}APP_EMAIL (Gmail/M365){RESET}: "),
        "APP_EMAIL_PASS": input(f"    {BOLD}APP_EMAIL_PASS{RESET}: "),
        "POSTGRES_DSN": "postgresql://hexclaw:hexclaw@localhost:5432/hexclaw",
        "REDIS_URL": "redis://localhost:6379/0"
    }

    with open(ENV_FILE, "w") as f:
        for k, v in config.items():
            f.write(f"{k}={v}\n")
    ok(".env file created.")

def setup_services():
    header("Step 3: Service Registration")
    is_linux = platform.system() == "Linux"
    if is_linux:
        service_path = Path("/etc/systemd/system/hexclaw.service")
        content = textwrap.dedent(f"""\
            [Unit]
            Description=HexClaw Agent
            After=network.target redis.service postgresql.service

            [Service]
            ExecStart={sys.executable} {ROOT}/daemon.py
            WorkingDirectory={ROOT}
            Restart=always
            EnvironmentFile={ENV_FILE}

            [Install]
            WantedBy=multi-user.target
        """)
        try:
            # Note: This usually requires sudo to write to /etc
            with open(ROOT / "hexclaw.service", "w") as f:
                f.write(content)
            ok(f"systemd unit written to {ROOT}/hexclaw.service (copy to /etc/systemd/system/)")
        except Exception as e:
            warn(f"Could not write service file: {e}")
    else:
        ok("Windows detected: Please use NSSM or Task Scheduler to run daemon.py.")

def check_infra():
    header("Step 4: Infrastructure Check")
    if shutil.which("redis-cli"): ok("Redis detected.")
    else: warn("Redis not found in PATH.")
    if shutil.which("psql"): ok("PostgreSQL detected.")
    else: warn("PostgreSQL not found in PATH.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"\n{BOLD}{CYAN}# HexClaw Orchestrator Installation{RESET}")
    if args.dry_run:
        header("Dry Run Mode")
        ok("Dependencies check skipped.")
        ok(".env would be created.")
        ok("Infrastructure would be checked.")
        ok("Services would be registered.")
        return

    install_deps()
    setup_env()
    check_infra()
    setup_services()
    header("Setup Complete")
    print(f"Run {BOLD}python daemon.py{RESET} to start.")

if __name__ == "__main__":
    main()
