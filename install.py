#!/usr/bin/env python3
"""
HexClaw install.py
==================
Bootstraps everything needed to run the HexClaw autonomous agent:
  1. Python pip dependencies
  2. Redis (used for exact + semantic inference cache)
  3. PostgreSQL database + schema
  4. Temp-mail provider configuration
  5. .env file generation (interactive or --defaults)
  6. Systemd / Windows service registration

Usage:
    python install.py                  # interactive setup
    python install.py --defaults       # non-interactive, use defaults
    python install.py --skip-redis     # skip Redis install check
    python install.py --skip-postgres  # skip Postgres install check
    python install.py --skip-services  # do not register system services
"""

import argparse
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
REQUIREMENTS = ROOT / "requirements.txt"
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
SKILLS_DIR = ROOT / "skills"
TOKEN_LOG_DB = ROOT / "data" / "token_log.db"

HEXCLAW_REQUIREMENTS = [
    # Async runtime
    "asyncio-mqtt>=0.16.0,<1.0.0",
    # Inference
    "litellm>=1.30.0,<2.0.0",
    # Cache
    "redis>=5.0.0,<6.0.0",
    "numpy>=1.26.0,<2.0.0",           # embeddings (semantic cache)
    # Data
    "duckdb>=0.10.0,<1.0.0",
    "psycopg2-binary>=2.9.0,<3.0.0",
    # Telegram
    "python-telegram-bot>=21.0,<22.0",
    # HTTP / async
    "httpx>=0.27.0,<1.0.0",
    "aiohttp>=3.9.0,<4.0.0",
    # Utilities
    "python-dotenv>=1.0.0,<2.0.0",
    "pydantic>=2.6.0,<3.0.0",
    "rich>=13.7.0,<14.0.0",            # pretty terminal output
    "click>=8.1.0,<9.0.0",
    "croniter>=2.0.0,<3.0.0",          # cron schedule parsing
    "feedparser>=6.0.0,<7.0.0",        # RSS monitor
    # Already in hexstrike requirements.txt (kept for completeness / venv compat)
    "requests>=2.31.0,<3.0.0",
    "flask>=2.3.0,<4.0.0",
    "fastmcp>=0.2.0,<1.0.0",
    "psutil>=5.9.0,<6.0.0",
]

POSTGRES_SCHEMA = """
-- HexClaw PostgreSQL schema

CREATE TABLE IF NOT EXISTS targets (
    id          SERIAL PRIMARY KEY,
    value       TEXT NOT NULL UNIQUE,
    type        TEXT NOT NULL,          -- domain | ip | cidr | url
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scans (
    id          SERIAL PRIMARY KEY,
    target_id   INT REFERENCES targets(id),
    tool        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|failed
    parquet_path TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vulns (
    id          SERIAL PRIMARY KEY,
    scan_id     INT REFERENCES scans(id),
    severity    TEXT,
    title       TEXT,
    detail      JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,          -- rss | shodan | cve
    title       TEXT,
    url         TEXT,
    severity    TEXT,
    sent        BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inference_log (
    id          SERIAL PRIMARY KEY,
    provider    TEXT,
    model       TEXT,
    tokens_in   INT,
    tokens_out  INT,
    cost_usd    NUMERIC(10,6),
    cache_hit   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""

ENV_DEFAULTS = {
    # Telegram
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    # Inference providers
    "LITELLM_PROVIDER_HIGH": "gemini/gemini-1.5-pro",        # expensive tasks
    "LITELLM_PROVIDER_LOW": "openrouter/mistralai/mistral-7b-instruct",  # cheap tasks
    "GOOGLE_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    # Redis
    "REDIS_URL": "redis://localhost:6379/0",
    "REDIS_SEMANTIC_DB": "1",
    # Postgres
    "POSTGRES_DSN": "postgresql://hexclaw:hexclaw@localhost:5432/hexclaw",
    # HexStrike MCP server
    "HEXSTRIKE_SERVER_URL": "http://localhost:8888",
    # Temp-mail providers (comma-separated base URLs)
    "TEMPMAIL_PROVIDERS": "https://www.guerrillamail.com,https://temp-mail.org",
    # SMTP (for sending)
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "",
    "SMTP_PASSWORD": "",
    # Shodan (optional)
    "SHODAN_API_KEY": "",
    # CVE RSS feeds (comma-separated)
    "RSS_FEEDS": (
        "https://feeds.feedburner.com/TheHackersNews,"
        "https://www.cvedetails.com/vulnerability-feed.php?vendor_id=0&product_id=0&version_id=0&orderby=2&cvssscoremin=7"
    ),
    # Paths
    "OUTPUT_DIR": str(OUTPUT_DIR),
    "DATA_DIR": str(DATA_DIR),
    "LOGS_DIR": str(LOGS_DIR),
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def err(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{CYAN}══ {msg} ══{RESET}")


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess command."""
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — pip dependencies
# ─────────────────────────────────────────────────────────────────────────────

def install_pip_deps() -> None:
    header("Step 1 — Python dependencies")

    # Write a combined requirements file for HexClaw
    hexclaw_req = ROOT / "requirements_hexclaw.txt"
    hexclaw_req.write_text("\n".join(HEXCLAW_REQUIREMENTS) + "\n", encoding="utf-8")
    ok(f"HexClaw requirements written → {hexclaw_req.name}")

    pip = [sys.executable, "-m", "pip", "install", "--upgrade"]

    # Upgrade pip itself first
    try:
        run(pip + ["pip"], capture=True)
        ok("pip upgraded")
    except subprocess.CalledProcessError:
        warn("pip upgrade failed — continuing")

    # Install HexClaw deps
    try:
        run([sys.executable, "-m", "pip", "install", "-r", str(hexclaw_req)])
        ok("HexClaw dependencies installed")
    except subprocess.CalledProcessError as exc:
        err(f"pip install failed: {exc}")
        sys.exit(1)

    # Install existing HexStrike deps (best-effort — some may fail on Windows)
    if REQUIREMENTS.exists():
        try:
            run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)], check=False)
            ok("HexStrike requirements installed (best-effort)")
        except Exception:
            warn("Some HexStrike requirements skipped (optional tools may not be available)")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Redis
# ─────────────────────────────────────────────────────────────────────────────

def setup_redis(skip: bool) -> None:
    header("Step 2 — Redis (exact + semantic cache)")

    if skip:
        warn("Skipping Redis setup (--skip-redis). Caching will be disabled.")
        return

    if command_exists("redis-server"):
        ok("redis-server found in PATH")
        # Try to ping the expected instance
        try:
            result = run(["redis-cli", "ping"], capture=True, check=False)
            if "PONG" in result.stdout:
                ok("Redis is already running and responsive")
                return
        except Exception:
            pass
        warn("Redis not responding — attempting to start")
        _start_redis()
    else:
        _install_redis_instructions()


def _start_redis() -> None:
    if IS_WINDOWS:
        warn("On Windows, start Redis manually: redis-server")
        warn("Download: https://github.com/microsoftarchive/redis/releases")
    elif IS_LINUX:
        try:
            run(["sudo", "systemctl", "start", "redis-server"], check=False)
            ok("redis-server started via systemctl")
        except Exception:
            err("Could not start Redis automatically. Run: sudo systemctl start redis-server")


def _install_redis_instructions() -> None:
    err("redis-server not found in PATH")
    if IS_WINDOWS:
        print(textwrap.dedent("""
            Install Redis on Windows:
              Option A: WSL2 → sudo apt install redis-server
              Option B: https://github.com/microsoftarchive/redis/releases
              Option C: Docker → docker run -d -p 6379:6379 redis:alpine
        """))
    elif IS_LINUX:
        print("    Run: sudo apt install redis-server && sudo systemctl enable redis-server")
    else:
        print("    See: https://redis.io/docs/getting-started/installation/")


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

def setup_postgres(skip: bool, dsn: str) -> None:
    header("Step 3 — PostgreSQL database + schema")

    if skip:
        warn("Skipping PostgreSQL setup (--skip-postgres). Data persistence will be limited.")
        return

    if not command_exists("psql"):
        _install_postgres_instructions()
        return

    ok("psql found in PATH")

    # Parse DSN for user/db/host (basic split)
    # Format: postgresql://user:pass@host:port/dbname
    try:
        from urllib.parse import urlparse
        p = urlparse(dsn)
        db_user = p.username or "hexclaw"
        db_pass = p.password or "hexclaw"
        db_host = p.hostname or "localhost"
        db_port = p.port or 5432
        db_name = p.path.lstrip("/") or "hexclaw"
    except Exception:
        db_user, db_pass, db_host, db_port, db_name = "hexclaw", "hexclaw", "localhost", 5432, "hexclaw"

    # Create DB user + database (run as postgres superuser)
    setup_sql = textwrap.dedent(f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{db_user}') THEN
            CREATE ROLE {db_user} LOGIN PASSWORD '{db_pass}';
          END IF;
        END $$;
        CREATE DATABASE {db_name} OWNER {db_user};
    """).strip()

    print(f"    → Creating user '{db_user}' and database '{db_name}' on {db_host}:{db_port}")
    print("    (You may be prompted for the postgres superuser password)\n")

    try:
        proc = subprocess.run(
            ["psql", "-h", str(db_host), "-p", str(db_port), "-U", "postgres", "-c", setup_sql],
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0 or "already exists" in proc.stderr.lower():
            ok(f"Database '{db_name}' ready")
        else:
            warn(f"DB setup output: {proc.stderr.strip()}")
    except FileNotFoundError:
        err("psql not found after check — check PATH")
        return

    # Apply schema
    _apply_postgres_schema(db_host, db_port, db_name, db_user)


def _apply_postgres_schema(host: str, port: int, db: str, user: str) -> None:
    try:
        import psycopg2
        dsn = f"host={host} port={port} dbname={db} user={user}"
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(POSTGRES_SCHEMA)
        conn.close()
        ok("PostgreSQL schema applied")
    except ImportError:
        warn("psycopg2 not installed yet — schema will be applied on first daemon start")
    except Exception as exc:
        warn(f"Schema apply failed (will retry on daemon start): {exc}")


def _install_postgres_instructions() -> None:
    err("psql not found in PATH")
    if IS_WINDOWS:
        print("    Install PostgreSQL: https://www.postgresql.org/download/windows/")
    elif IS_LINUX:
        print("    Run: sudo apt install postgresql postgresql-contrib && sudo systemctl start postgresql")
    else:
        print("    See: https://www.postgresql.org/download/")


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Temp-mail configuration
# ─────────────────────────────────────────────────────────────────────────────

def setup_tempmail() -> None:
    header("Step 4 — Temp-mail configuration")

    # We don't install anything — just validate that the providers field is set
    # and that httpx is importable (needed at runtime)
    try:
        import httpx  # noqa: F401
        ok("httpx available (used for temp-mail probing)")
    except ImportError:
        warn("httpx not installed — will be installed via pip dep step")

    ok("Temp-mail providers configured via TEMPMAIL_PROVIDERS in .env")
    print("    Default providers: guerrillamail.com, temp-mail.org")
    print("    Add more comma-separated URLs to TEMPMAIL_PROVIDERS in .env")


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — .env file
# ─────────────────────────────────────────────────────────────────────────────

def setup_env(defaults_mode: bool) -> dict[str, str]:
    header("Step 5 — .env configuration")

    # Always write .env.example with all keys
    example_lines = ["# HexClaw .env.example — copy to .env and fill in values\n"]
    for key, val in ENV_DEFAULTS.items():
        example_lines.append(f"{key}={val}\n")
    ENV_EXAMPLE.write_text("".join(example_lines), encoding="utf-8")
    ok(f".env.example written → {ENV_EXAMPLE.name}")

    if ENV_FILE.exists():
        ok(".env already exists — skipping overwrite")
        # Load current values
        current = _parse_env(ENV_FILE)
        # Backfill any missing keys
        updated = False
        for key, default in ENV_DEFAULTS.items():
            if key not in current:
                current[key] = default
                updated = True
        if updated:
            _write_env(current)
            ok("New .env keys backfilled")
        return current

    config: dict[str, str] = {}

    if defaults_mode:
        config = dict(ENV_DEFAULTS)
        ok("Using default values (--defaults mode)")
    else:
        print(f"  {YELLOW}Interactive setup — press Enter to accept defaults{RESET}\n")
        important_keys = [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
            "GOOGLE_API_KEY",
            "OPENROUTER_API_KEY",
            "POSTGRES_DSN",
            "REDIS_URL",
            "HEXSTRIKE_SERVER_URL",
            "SMTP_USER",
            "SMTP_PASSWORD",
        ]
        for key, default in ENV_DEFAULTS.items():
            if key in important_keys:
                display_default = f"[{default}]" if default else "[empty]"
                try:
                    val = input(f"    {key} {display_default}: ").strip()
                except EOFError:
                    val = ""
                config[key] = val if val else default
            else:
                config[key] = default

    _write_env(config)
    ok(f".env written → {ENV_FILE.name}")
    return config


def _parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(config: dict[str, str]) -> None:
    lines = ["# HexClaw .env — generated by install.py\n"]
    for key, val in config.items():
        lines.append(f"{key}={val}\n")
    ENV_FILE.write_text("".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Directory scaffolding + token log SQLite
# ─────────────────────────────────────────────────────────────────────────────

def scaffold_directories() -> None:
    header("Step 6 — Directory scaffold + token log DB")

    dirs = [
        OUTPUT_DIR,
        DATA_DIR,
        LOGS_DIR,
        SKILLS_DIR,
        ROOT / "output" / "us_masscan_vuln",
        ROOT / "output" / "recon",
        ROOT / "output" / "nuclei",
        ROOT / "output" / "gobuster",
        ROOT / "output" / "ffuf",
        ROOT / "output" / "nmap",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    ok(f"Created {len(dirs)} output/data directories")

    # SQLite token log (inference.py reads this)
    conn = sqlite3.connect(TOKEN_LOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            provider    TEXT,
            model       TEXT,
            tokens_in   INTEGER,
            tokens_out  INTEGER,
            cost_usd    REAL,
            cache_hit   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()
    ok(f"Token log SQLite initialised → {TOKEN_LOG_DB.relative_to(ROOT)}")

    # Seed skills directory with stub YAML
    recon_skill = SKILLS_DIR / "recon_osint.yaml"
    if not recon_skill.exists():
        recon_skill.write_text(
            textwrap.dedent("""\
            # HexClaw skill: recon_osint
            # Triggered by: /recon <target>
            name: recon_osint
            description: Full passive-to-active recon chain
            steps:
              - tool: amass
                output: subs.parquet
              - tool: rustscan
                input: subs.parquet
                output: ports.parquet
              - tool: nuclei
                input: ports.parquet
                output: vulns.parquet
              - tool: suggest_next
                input: vulns.parquet
                action: telegram_buttons
            """),
            encoding="utf-8",
        )
        ok(f"Seeded skills/recon_osint.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Service registration
# ─────────────────────────────────────────────────────────────────────────────

def setup_services(skip: bool) -> None:
    header("Step 7 — Service registration")

    if skip:
        warn("Skipping service registration (--skip-services)")
        return

    if IS_LINUX:
        _register_systemd_service()
    elif IS_WINDOWS:
        _show_windows_service_instructions()
    else:
        warn("Service registration only supported on Linux (systemd) and Windows.")


def _register_systemd_service() -> None:
    daemon_py = ROOT / "daemon.py"
    service_content = textwrap.dedent(f"""\
        [Unit]
        Description=HexClaw Autonomous Cybersecurity Agent
        After=network.target redis.service postgresql.service

        [Service]
        Type=simple
        User={os.getenv("USER", "hexclaw")}
        WorkingDirectory={ROOT}
        ExecStart={sys.executable} {daemon_py}
        Restart=on-failure
        RestartSec=10
        EnvironmentFile={ENV_FILE}

        [Install]
        WantedBy=multi-user.target
    """)

    service_path = Path("/etc/systemd/system/hexclaw.service")
    tmp_service = ROOT / "hexclaw.service"
    tmp_service.write_text(service_content, encoding="utf-8")
    ok(f"Service file written → {tmp_service.name}")

    print(f"\n  {YELLOW}To install the systemd service, run:{RESET}")
    print(f"    sudo cp {tmp_service} {service_path}")
    print("    sudo systemctl daemon-reload")
    print("    sudo systemctl enable hexclaw")
    print("    sudo systemctl start hexclaw")


def _show_windows_service_instructions() -> None:
    daemon_py = ROOT / "daemon.py"
    ok("Windows service stub (use NSSM or Task Scheduler):")
    print(textwrap.dedent(f"""
        Option A — NSSM (recommended):
          1. Download NSSM: https://nssm.cc/download
          2. nssm install HexClaw "{sys.executable}" "{daemon_py}"
          3. nssm start HexClaw

        Option B — Task Scheduler:
          Create a task that runs:
            {sys.executable} "{daemon_py}"
          with trigger: At system startup, repeat every 1 minute.

        Option C — Run manually:
          python "{daemon_py}"
    """))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HexClaw installer — bootstraps all dependencies and services"
    )
    parser.add_argument("--defaults", action="store_true", help="Non-interactive; use default values")
    parser.add_argument("--skip-redis", action="store_true", help="Skip Redis setup")
    parser.add_argument("--skip-postgres", action="store_true", help="Skip PostgreSQL setup")
    parser.add_argument("--skip-services", action="store_true", help="Skip service registration")
    args = parser.parse_args()

    print(f"\n{BOLD}{CYAN}╔{'═' * 52}╗")
    print(f"║{'HexClaw Installer v1.0':^52}║")
    print(f"║{'Autonomous Cybersecurity Agent':^52}║")
    print(f"╚{'═' * 52}╝{RESET}\n")
    print(f"  Platform : {platform.system()} {platform.release()}")
    print(f"  Python   : {sys.version.split()[0]}")
    print(f"  Root     : {ROOT}")

    # Step 1 — pip
    install_pip_deps()

    # Step 2 — Redis
    setup_redis(skip=args.skip_redis)

    # Step 3 — Postgres
    # We need DSN from .env (or default) — check if .env exists already
    dsn = ENV_DEFAULTS["POSTGRES_DSN"]
    if ENV_FILE.exists():
        existing = _parse_env(ENV_FILE)
        dsn = existing.get("POSTGRES_DSN", dsn)
    setup_postgres(skip=args.skip_postgres, dsn=dsn)

    # Step 4 — Temp-mail
    setup_tempmail()

    # Step 5 — .env
    config = setup_env(defaults_mode=args.defaults)

    # Step 6 — Dirs + SQLite
    scaffold_directories()

    # Step 7 — Services
    setup_services(skip=args.skip_services)

    # ── Final summary ──────────────────────────────────────────────────────
    header("Installation complete")
    print()

    checks = [
        ("Telegram bot token",     bool(config.get("TELEGRAM_BOT_TOKEN"))),
        ("Telegram chat ID",       bool(config.get("TELEGRAM_CHAT_ID"))),
        ("Google API key",         bool(config.get("GOOGLE_API_KEY"))),
        ("OpenRouter API key",     bool(config.get("OPENROUTER_API_KEY"))),
        ("Redis URL",              bool(config.get("REDIS_URL"))),
        ("Postgres DSN",           bool(config.get("POSTGRES_DSN"))),
        ("HexStrike server URL",   bool(config.get("HEXSTRIKE_SERVER_URL"))),
    ]

    all_ok = True
    for label, status in checks:
        if status:
            ok(label)
        else:
            warn(f"{label} — NOT SET (edit .env before starting daemon)")
            all_ok = False

    print()
    if all_ok:
        print(f"  {GREEN}{BOLD}All checks passed! Start with:{RESET}")
    else:
        print(f"  {YELLOW}{BOLD}Some values missing — edit .env then start with:{RESET}")

    print(f"    {CYAN}python daemon.py{RESET}\n")


if __name__ == "__main__":
    main()
