"""
HexClaw — daemon.py
===================
The core asyncio orchestrator for the HexClaw autonomous agent.

PRD v1.0 Rules:
  • Heartbeat poll sqlite queue.
  • Run MCP YAML workflows (Skills).
  • Telegram notify (chat_id, msg, file).
  • Redis startup check.
  • Run forever.
"""

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

import telegram as tg_module
from telegram import Notifier, register_enqueue, register_status, register_orchestrate
import planner
import cache
import inference
import monitor

load_dotenv()

# ── Null Notifier (for testing) ────────────────────────────────────────────────
class NullNotifier:
    async def send(self, text: str, parse_mode: str = "Markdown"): pass
    async def send_file(self, file_path: str, caption: str | None = None): pass
    async def send_report(self, *args, **kwargs): pass

# ── Config ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"
JOBS_DB = DATA_DIR / "jobs.db"
SKILLS_DIR = ROOT / "skills"
LOG_DIR = ROOT / "logs"

LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "daemon.log")
    ]
)
log = logging.getLogger("hexclaw.daemon")

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(JOBS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            skill TEXT,
            params TEXT,
            status TEXT DEFAULT 'pending',
            target TEXT,
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            result TEXT,
            error TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ── Job Lifecycle ─────────────────────────────────────────────────────────────
class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

async def enqueue_job(skill: str, params: dict) -> str:
    job_id = str(uuid.uuid4())[:8]
    target = params.get("target", "unknown")
    conn = sqlite3.connect(JOBS_DB)
    conn.execute(
        "INSERT INTO jobs (id, skill, params, target, created_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, skill, json.dumps(params), target, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()
    log.info(f"Enqueued job {job_id}: {skill} on {target}")
    return job_id

def get_pending_jobs():
    conn = sqlite3.connect(JOBS_DB)
    conn.row_factory = sqlite3.Row
    jobs = conn.execute("SELECT * FROM jobs WHERE status = ?", (JobStatus.PENDING,)).fetchall()
    conn.close()
    return jobs

def get_recent_jobs(limit=10):
    conn = sqlite3.connect(JOBS_DB)
    conn.row_factory = sqlite3.Row
    jobs = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(j) for j in jobs]

def update_job_status(job_id: str, status: str, result: Any = None, error: str = None):
    conn = sqlite3.connect(JOBS_DB)
    now = datetime.now(timezone.utc).isoformat()
    if status == JobStatus.RUNNING:
        conn.execute("UPDATE jobs SET status = ?, started_at = ? WHERE id = ?", (status, now, job_id))
    elif status in (JobStatus.DONE, JobStatus.FAILED):
        conn.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, result = ?, error = ? WHERE id = ?",
            (status, now, json.dumps(result) if result else None, error, job_id)
        )
    conn.commit()
    conn.close()

# ── Skills & MCP ──────────────────────────────────────────────────────────────
async def run_skill(job_id: str, skill_name: str, params: dict, notifier: Notifier | NullNotifier):
    log.info(f"Starting skill execution: {skill_name} (Job: {job_id})")
    update_job_status(job_id, JobStatus.RUNNING)
    
    skill_file = SKILLS_DIR / f"{skill_name}.yaml"
    if not skill_file.exists():
        err = f"Skill {skill_name} not found"
        update_job_status(job_id, JobStatus.FAILED, error=err)
        await notifier.send(f"❌ Job {job_id} failed: {err}")
        return

    with open(skill_file, "r") as f:
        skill_def = yaml.safe_load(f)

    steps = skill_def.get("steps", [])
    context = params.copy()
    
    for i, step in enumerate(steps, 1):
        tool = step.get("tool")
        log.info(f"Step {i}/{len(steps)}: Running {tool}")
        # Placeholder for MCP tool call logic
        # In v1.1 we would call http://localhost:8888/api/tools/...
        await notifier.send(f"🔄 Job {job_id} step {i}: {tool}...")
        await asyncio.sleep(1) # Simulating work

    update_job_status(job_id, JobStatus.DONE, result={"status": "completed"})
    await notifier.send(f"✅ Job {job_id} complete!")

# ── Daemon ────────────────────────────────────────────────────────────────────
class HexClawDaemon:
    def __init__(self):
        self._stop_event = asyncio.Event()
        self.notifier = NullNotifier()

    async def orchestrate(self, goal: str) -> str:
        """Translate goal to skill and enqueue."""
        plan = planner.plan_goal(goal)
        skill = plan.get("skill", "agent_plan")
        params = plan.get("params", {})
        if "goal" not in params:
            params["goal"] = goal
        return await enqueue_job(skill, params)

    async def start(self):
        header_text = "HexClaw Daemon v1.0 Starting"
        log.info(header_text)
        
        # Redis Startup Check
        try:
            r_status = cache.get_cache().stats()
            log.info(f"Redis Cache Ready: {r_status}")
        except Exception as e:
            log.warning(f"Redis Cache connection failed: {e}")

        # Telegram Init
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        register_enqueue(enqueue_job)
        register_status(get_recent_jobs)
        register_orchestrate(self.orchestrate)

        if token and chat_id:
            self.notifier = Notifier(token, int(chat_id))
            await self.notifier.send("🦾 HexClaw Daemon Online (v1.0)")
            
            # Start Telegram Bot
            asyncio.create_task(tg_module.run_bot_async())
            
            # Start Monitor
            m = monitor.get_monitor(notifier=self.notifier)
            asyncio.create_task(m.run())
            log.info("Threat Monitor active.")
        else:
            log.warning("Telegram not configured. Running in terminal-only mode.")

    async def run_forever(self):
        await self.start()
        log.info("Daemon heartbeat active.")
        while not self._stop_event.is_set():
            pending = get_pending_jobs()
            for row in pending:
                job_id = row['id']
                skill = row['skill']
                params = json.loads(row['params'])
                asyncio.create_task(run_skill(job_id, skill, params, self.notifier))
            
            await asyncio.sleep(5) # Heartbeat interval

async def main():
    daemon = HexClawDaemon()
    await daemon.run_forever()

if __name__ == "__main__":
    asyncio.run(main())
