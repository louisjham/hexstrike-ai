# HexClaw — Kali Linux WSL Installation Guide

> **Tested on:** Kali Linux 2024.x (WSL 2) · Python 3.11+ · Windows 10/11

---

## 1. Prerequisites

### 1.1 Install WSL + Kali

Open **PowerShell (Admin)** on Windows:

```powershell
# Enable WSL (one-time)
wsl --install

# Install Kali Linux
wsl --install -d kali-linux

# Verify
wsl -l -v
#  NAME           STATE    VERSION
#  kali-linux     Running  2
```

After first launch, create a user and password when prompted.

### 1.2 Update Kali

```bash
sudo apt update && sudo apt full-upgrade -y
```

---

## 2. System Dependencies

```bash
# Python + build tools
sudo apt install -y python3 python3-pip python3-venv git curl

# Redis (inference cache)
sudo apt install -y redis-server
sudo systemctl enable redis-server --now

# PostgreSQL (optional — data.py analytics)
sudo apt install -y postgresql postgresql-client
sudo systemctl enable postgresql --now

# Kali meta-packages (the tools HexStrike wraps)
sudo apt install -y kali-tools-top10     # nmap, sqlmap, hydra, etc.
sudo apt install -y amass subfinder httpx-toolkit nuclei masscan ffuf rustscan
```

### 2.1 Verify Key Tools

```bash
nmap --version
nuclei -version
amass -version
redis-cli ping          # → PONG
```

---

## 3. Clone & Virtual Environment

```bash
cd ~
git clone <your-repo-url> hexstrike-ai
cd hexstrike-ai

python3 -m venv .venv
source .venv/bin/activate

# Core deps
pip install --upgrade pip
pip install -r requirements.txt

# HexClaw agent deps (not in requirements.txt)
pip install litellm python-telegram-bot redis duckdb \
            psycopg2-binary python-dotenv pyyaml pandas httpx pyarrow feedparser
```

> **Tip:** Run `python install.py` for an interactive setup if you prefer a wizard.

---

## 4. Environment Configuration

Create `.env` in the project root:

```bash
cat > .env << 'EOF'
# ── Telegram (REQUIRED) ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>

# ── AI Provider Keys ─────────────────────────────────────────────────────────
GOOGLE_API_KEY=<gemini-api-key>
# OPENROUTER_API_KEY=<optional>
# ZHIPUAI_API_KEY=<optional>

# ── Infrastructure ───────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
POSTGRES_DSN=postgresql://hexclaw:hexclaw@localhost:5432/hexclaw

# ── Monitor ──────────────────────────────────────────────────────────────────
# SHODAN_API_KEY=<optional>
# MONITOR_INTERVAL_SEC=900
# ALERT_MIN_SEVERITY=medium

# ── Email (optional) ─────────────────────────────────────────────────────────
# APP_EMAIL=<gmail-or-m365>
# APP_EMAIL_PASS=<app-password>
# M365_EMAIL=<m365-email>
# M365_PASS=<m365-password>

# ── Logging ──────────────────────────────────────────────────────────────────
# TG_LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
# TG_LOG_BATCH_SEC=3         # batch interval for log forwarding
EOF

chmod 600 .env
```

### 4.1 Getting a Telegram Bot Token

1. Message **@BotFather** on Telegram
2. Send `/newbot` → follow prompts → copy the token
3. Add the bot to your group/DM it once
4. Get your chat ID:
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool | grep '"id"'
   ```

---

## 5. Database Setup (Optional)

### PostgreSQL

```bash
sudo -u postgres psql -c "CREATE USER hexclaw WITH PASSWORD 'hexclaw';"
sudo -u postgres psql -c "CREATE DATABASE hexclaw OWNER hexclaw;"
```

### Redis

```bash
redis-cli ping   # → PONG
```

SQLite databases (`jobs.db`, `token_log.db`) are created automatically in `./data/`.

---

## 6. Run HexClaw

### 6.1 Quick Test (foreground)

```bash
source .venv/bin/activate
python3 daemon.py
```

You should see:
```
HexClaw Daemon v1.0 Starting
Redis Cache Ready: {...}
🦾 HexClaw Daemon Online (v1.0)    ← also appears in Telegram
```

### 6.2 Systemd Service (persist across reboots)

```bash
# Generate the unit file
python3 install.py

# Install it
sudo cp hexclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hexclaw --now

# Verify
sudo systemctl status hexclaw
journalctl -u hexclaw -f    # live logs
```

---

## 7. Verification Checklist

Open your Telegram chat and run these commands:

| Command | What It Does |
|---------|-------------|
| `/help` | List all commands |
| `/status` | Active jobs + analytics |
| `/stats` | Inference cost dashboard |
| `/recon <target>` | Start recon chain |
| `/orchestrate <goal>` | AI-planned attack chain |
| `/data <query>` | Natural language SQL |

---

## 8. Folder Structure

```
hexstrike-ai/
├── .env                 # Secrets (gitignored)
├── config.py            # Shared path constants
├── daemon.py            # Core orchestrator
├── telegram.py          # Bot interface + Notifier
├── tg_log.py            # Telegram log handler (centralised visibility)
├── inference.py         # LLM engine (multi-provider)
├── cache.py             # Two-tier Redis cache
├── data.py              # DuckDB analytics
├── monitor.py           # Threat intel monitor
├── planner.py           # Goal → skill planner
├── vuln_prioritize.py   # CVE prioritizer
├── install.py           # Bootstrap wizard
├── skills/              # YAML skill definitions
│   ├── recon_osint.yaml
│   ├── agent_plan.yaml
│   └── ...
├── data/                # SQLite DBs + Parquet files
├── logs/                # File-based logs
└── hexstrike_mcp.py     # MCP tool server (150+ tools)
```

---

## 9. Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: telegram` | `pip install python-telegram-bot` |
| Redis connection refused | `sudo systemctl start redis-server` |
| Telegram bot not responding | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
| Permission denied on port scan | Run with `sudo` or add capabilities: `sudo setcap cap_net_raw+ep $(which nmap)` |
| WSL networking issues | `wsl --shutdown` from PowerShell, then reopen Kali |
| `litellm` API errors | Verify `GOOGLE_API_KEY` is set; check `python3 -c "import litellm; print('ok')"` |
| SQLite locked | Only one daemon instance should run at a time |

---

## 10. Security Notes

- **`.env` contains secrets** — never commit it (`echo .env >> .gitignore`)
- **Bot access** is restricted to `TELEGRAM_CHAT_ID` — unauthorized users are rejected
- **All tool execution** requires operator approval via Telegram inline buttons
- **WSL shares the Windows network** — exposed services are accessible from Windows
