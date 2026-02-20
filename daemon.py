"""
HexClaw — daemon.py
===================
The core asyncio orchestrator for the HexClaw autonomous agent.

Responsibilities:
  1. Heartbeat loop — poll the job queue every N seconds
  2. Skill execution — load YAML skill files, chain MCP tool calls
  3. Telegram notifications — report progress/results to operator
  4. Human-in-the-loop gates — pause and await operator approval
  5. Monitor integration — consume CVE/RSS alerts from monitor.py
  6. Graceful shutdown — cancel tasks on SIGINT/SIGTERM

Architecture:
  ┌──────────────┐   enqueue()   ┌─────────────────┐
  │ telegram.py  │ ────────────► │   Job Queue      │ (asyncio.Queue)
  │  /recon cmd  │               │   (in-memory +   │
  └──────────────┘               │    Postgres)     │
                                 └────────┬─────────┘
                                          │ poll
                                 ┌────────▼─────────┐
                                 │  SkillRunner      │
                                 │  recon_osint.yaml │
                                 │  amass→rustscan   │
                                 │  →nuclei→suggest  │
                                 └────────┬─────────┘
                                          │ results
                                 ┌────────▼─────────┐
                                 │  Notifier         │
                                 │  (telegram.py)    │
                                 └──────────────────┘

Usage:
    python daemon.py            # run forever
    python daemon.py --once     # drain queue once and exit
    python daemon.py --dry-run  # parse skills but don't call MCP
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Local modules ─────────────────────────────────────────────────────────────
import telegram as tg_module
from telegram import Notifier, register_enqueue, register_status

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "daemon.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("hexclaw.daemon")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
SKILLS_DIR = ROOT / "skills"
DATA_DIR = ROOT / "data"

HEXSTRIKE_URL: str = os.getenv("HEXSTRIKE_SERVER_URL", "http://localhost:8888")
TELEGRAM_CHAT_ID: int = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
POSTGRES_DSN: str = os.getenv("POSTGRES_DSN", "")

# Heartbeat interval (seconds between queue drain cycles)
HEARTBEAT_SEC: int = int(os.getenv("DAEMON_HEARTBEAT_SEC", "5"))

# Max concurrent skill runners
MAX_CONCURRENT_JOBS: int = int(os.getenv("DAEMON_MAX_CONCURRENT", "3"))

# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job:
    """In-memory job record."""

    def __init__(self, skill: str, params: dict[str, Any]) -> None:
        self.id: str = str(uuid.uuid4())[:8]
        self.skill: str = skill
        self.params: dict[str, Any] = params
        self.target: str = params.get("target", "unknown")
        self.status: str = JobStatus.PENDING
        self.created_at: datetime = datetime.now(timezone.utc)
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None

    @property
    def elapsed_sec(self) -> int | None:
        if self.started_at is None:
            return None
        end = self.finished_at or datetime.now(timezone.utc)
        return int((end - self.started_at).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill": self.skill,
            "target": self.target,
            "status": self.status,
            "elapsed_sec": self.elapsed_sec,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Skill loader
# ─────────────────────────────────────────────────────────────────────────────

def load_skill(name: str) -> dict[str, Any]:
    """
    Load a skill YAML from skills/<name>.yaml.
    Returns the parsed skill definition dict.
    """
    try:
        import yaml
    except ImportError:
        # Fallback: minimal inline parser for simple YAML
        yaml = None  # type: ignore

    skill_file = SKILLS_DIR / f"{name}.yaml"
    if not skill_file.exists():
        raise FileNotFoundError(f"Skill file not found: {skill_file}")

    text = skill_file.read_text(encoding="utf-8")

    if yaml:
        return yaml.safe_load(text)

    # Fallback minimal parser (handles the recon_osint.yaml format)
    skill: dict[str, Any] = {"steps": []}
    current_step: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("name:"):
            skill["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("description:"):
            skill["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("- tool:"):
            if current_step:
                skill["steps"].append(current_step)
            current_step = {"tool": line.split(":", 1)[1].strip()}
        elif current_step is not None:
            for key in ("input", "output", "action"):
                if line.startswith(f"{key}:"):
                    current_step[key] = line.split(":", 1)[1].strip()
    if current_step:
        skill["steps"].append(current_step)

    return skill


# ─────────────────────────────────────────────────────────────────────────────
# MCP tool caller
# ─────────────────────────────────────────────────────────────────────────────

TOOL_ENDPOINT_MAP: dict[str, str] = {
    "amass":     "api/tools/amass-enum",
    "rustscan":  "api/tools/rustscan-fast-scan",
    "masscan":   "api/tools/masscan-high-speed",
    "nuclei":    "api/tools/nuclei",
    "nmap":      "api/tools/nmap-scan",
    "gobuster":  "api/tools/gobuster",
    "ffuf":      "api/tools/ffuf",
    "httpx":     "api/tools/httpx",
    "subfinder": "api/tools/subfinder",
    "suggest_next": None,  # handled internally — no MCP call
}


async def call_mcp_tool(
    tool: str,
    payload: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    POST to the HexStrike MCP server's tool endpoint.

    Returns the parsed JSON response, or a synthetic result on error.
    """
    endpoint = TOOL_ENDPOINT_MAP.get(tool)

    if endpoint is None:
        # Internal tool — no HTTP call
        return {"success": True, "tool": tool, "internal": True, "data": payload}

    if dry_run:
        log.info("[DRY RUN] Would call %s/%s with %s", HEXSTRIKE_URL, endpoint, payload)
        return {"success": True, "tool": tool, "dry_run": True}

    url = f"{HEXSTRIKE_URL.rstrip('/')}/{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("MCP tool %s HTTP %s: %s", tool, exc.response.status_code, exc.response.text[:200])
        return {"success": False, "tool": tool, "error": str(exc)}
    except Exception as exc:
        log.error("MCP tool %s error: %s", tool, exc)
        return {"success": False, "tool": tool, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Skill runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_skill(job: Job, notifier: Notifier, dry_run: bool = False) -> None:
    """
    Execute a skill YAML chain step-by-step, persisting Parquet outputs
    and notifying Telegram at each stage.

    PRD workflow for recon_osint:
      amass → subs.parquet
      rustscan → ports.parquet
      nuclei → vulns.parquet
      suggest_next → Telegram buttons
    """
    log.info("▶ Starting skill '%s' for target '%s' (job %s)", job.skill, job.target, job.id)
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)

    try:
        skill_def = load_skill(job.skill)
    except FileNotFoundError as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        await notifier.send(f"❌ Job `{job.id}`: skill `{job.skill}` not found.")
        return

    steps = skill_def.get("steps", [])
    context: dict[str, Any] = {"target": job.target, **job.params}
    all_findings: list[dict[str, Any]] = []

    # ── Step execution loop ───────────────────────────────────────────────
    for i, step in enumerate(steps, 1):
        tool = step.get("tool", "")
        output_key = step.get("output", "")
        action = step.get("action", "")

        # Check cancellation
        if tg_module.is_cancelled(job.id):
            tg_module.clear_cancel(job.id)
            job.status = JobStatus.CANCELLED
            await notifier.send(f"🚫 Job `{job.id}` cancelled at step {i}/{len(steps)} (`{tool}`).")
            return

        log.info("  Step %d/%d: %s → %s", i, len(steps), tool, output_key or action)
        await notifier.send(
            f"🔄 Job `{job.id}` step {i}/{len(steps)}: `{tool}` on `{job.target}`..."
        )

        # ── Internal: suggest_next ────────────────────────────────────────
        if tool == "suggest_next":
            await _handle_suggest_next(job, notifier, all_findings, context)
            continue

        # ── Build payload for this tool ───────────────────────────────────
        payload = _build_payload(tool, step, context)

        # ── Call MCP ─────────────────────────────────────────────────────
        result = await call_mcp_tool(tool, payload, dry_run=dry_run)

        if not result.get("success"):
            err_msg = result.get("error", "unknown error")
            log.warning("  Tool %s failed: %s", tool, err_msg)
            await notifier.send(
                f"⚠️ Job `{job.id}` step {i}: `{tool}` failed — `{err_msg}`\n"
                f"Continuing chain..."
            )
            continue

        # ── Persist output to Parquet ─────────────────────────────────────
        if output_key:
            parquet_path = await _persist_parquet(job, tool, output_key, result)
            context[output_key] = parquet_path
            log.info("  Saved → %s", parquet_path)

        # ── Accumulate findings ───────────────────────────────────────────
        findings = _extract_findings(tool, result)
        all_findings.extend(findings)
        context[f"{tool}_result"] = result

    # ── Skill complete ────────────────────────────────────────────────────
    job.status = JobStatus.DONE
    job.finished_at = datetime.now(timezone.utc)
    job.result = {"findings": all_findings}

    top_findings = [f.get("title", str(f)) for f in all_findings[:5]]
    await notifier.send_report(
        job_id=job.id,
        target=job.target,
        skill=job.skill,
        findings=all_findings,
        top_findings=top_findings,
        next_steps=None,  # suggest_next step handled inline above
    )
    log.info("✅ Job %s complete. %d findings.", job.id, len(all_findings))

    # Persist to Postgres (best-effort)
    await _persist_job_postgres(job, all_findings)


def _build_payload(tool: str, step: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """
    Build the MCP POST body for a tool step.
    Maps skill step format to the expected HexStrike API fields.
    """
    target = context.get("target", "")

    base: dict[str, Any] = {}

    if tool == "amass":
        base = {"domain": target, "mode": "passive", "max_time": 120}
    elif tool == "rustscan":
        base = {"target": target, "timeout": 3000, "batch_size": 4500}
    elif tool == "nuclei":
        # If we have a ports parquet, try to extract hosts from context
        base = {"target": target, "severity": "medium,high,critical", "timeout": 120}
    elif tool == "subfinder":
        base = {"domain": target}
    elif tool == "httpx":
        base = {"target": target, "timeout": 30}
    elif tool == "nmap":
        base = {"target": target, "scan_profile": "quick"}
    elif tool == "gobuster":
        base = {"url": f"http://{target}", "mode": "dir", "wordlist": "/usr/share/wordlists/dirb/common.txt"}
    else:
        base = {"target": target}

    # Merge any step-level extra params
    for k, v in step.items():
        if k not in ("tool", "input", "output", "action") and k not in base:
            base[k] = v

    return base


async def _persist_parquet(
    job: Job,
    tool: str,
    output_key: str,
    result: dict[str, Any],
) -> str:
    """
    Write tool result to a Parquet file in data/<job_id>/<output_key>.
    Returns the file path string.

    Falls back to JSON if DuckDB/pyarrow not available.
    """
    out_dir = DATA_DIR / job.id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Try Parquet via DuckDB
    try:
        import duckdb
        parquet_path = str(out_dir / f"{output_key}.parquet")

        # Flatten result to a list of records for DuckDB
        records = _result_to_records(tool, result)
        if records:
            con = duckdb.connect()
            con.execute("CREATE TABLE tmp AS SELECT * FROM ?", [records])
            con.execute(f"COPY tmp TO '{parquet_path}' (FORMAT PARQUET)")
            con.close()
        else:
            # Write empty placeholder
            Path(parquet_path).touch()
        return parquet_path

    except Exception as exc:
        log.debug("Parquet write failed (%s), falling back to JSON: %s", tool, exc)

    # Fallback: JSON
    json_path = str(out_dir / f"{output_key}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return json_path


def _result_to_records(tool: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert raw MCP result to a flat list of dicts suitable for DuckDB."""
    if tool == "amass":
        return [{"subdomain": s} for s in result.get("subdomains", [])]
    elif tool == "rustscan":
        ports = result.get("open_ports", [])
        if isinstance(ports, list):
            return [{"port": p} if isinstance(p, int) else p for p in ports]
    elif tool == "nuclei":
        return result.get("vulnerabilities", [])
    elif tool == "subfinder":
        return [{"subdomain": s} for s in result.get("subdomains", [])]

    # Generic fallback: wrap entire result
    return [{"raw": json.dumps(result)}]


def _extract_findings(tool: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalised finding dicts from a tool result."""
    findings: list[dict[str, Any]] = []

    if tool == "nuclei":
        for v in result.get("vulnerabilities", []):
            findings.append({
                "tool": "nuclei",
                "severity": v.get("severity", "info"),
                "title": v.get("template", "nuclei finding"),
                "detail": v.get("detail", ""),
            })
    elif tool == "amass":
        for sub in result.get("subdomains", [])[:50]:
            findings.append({"tool": "amass", "severity": "info", "title": sub, "detail": ""})
    elif tool == "rustscan":
        for port in result.get("open_ports", [])[:50]:
            findings.append({"tool": "rustscan", "severity": "info", "title": str(port), "detail": ""})
    else:
        # Generic
        raw_findings = result.get("findings", result.get("vulnerabilities", []))
        for f in (raw_findings if isinstance(raw_findings, list) else []):
            if isinstance(f, dict):
                findings.append({
                    "tool": tool,
                    "severity": f.get("severity", "info"),
                    "title": f.get("title", f.get("name", str(f))),
                    "detail": f.get("detail", ""),
                })

    return findings


async def _handle_suggest_next(
    job: Job,
    notifier: Notifier,
    findings: list[dict[str, Any]],
    context: dict[str, Any],
) -> None:
    """
    Zero-inference suggest_next step:
    - Compute next actions from findings using rules (no LLM)
    - Show as Telegram inline buttons for operator approval
    """
    severities = [f.get("severity", "info").lower() for f in findings]
    has_critical = "critical" in severities
    has_high = "high" in severities
    subs = [f["title"] for f in findings if f.get("tool") == "amass"][:5]
    ports = [f["title"] for f in findings if f.get("tool") == "rustscan"]

    # Rule-based next step suggestions (0 inference)
    suggestions: list[str] = []
    if has_critical or has_high:
        suggestions.append("nuclei_deep (critical/high templates only)")
    if subs:
        suggestions.append(f"subdomain_enum ({len(subs)} subs found)")
    if "80" in ports or "443" in ports:
        suggestions.append("web_vuln_scan (HTTP found)")
    if "22" in ports:
        suggestions.append("ssh_audit")
    if not suggestions:
        suggestions.append("manual_review")

    choices = suggestions[:4]  # max 4 buttons

    prompt = (
        f"🎯 *Job `{job.id}` complete for `{job.target}`*\n"
        f"Found: {len(findings)} items · "
        f"{'🔴 CRITICAL' if has_critical else '🟠 HIGH' if has_high else '🟡 MEDIUM'}\n\n"
        f"Select next action:"
    )

    if TELEGRAM_CHAT_ID and BOT_TOKEN:
        result = await notifier.request_approval(
            approval_id=f"suggest_{job.id}",
            prompt=prompt,
            choices=choices,
            timeout_sec=120,
        )
        chosen = result.get("choice") or result.get("action", "skipped")
        log.info("Operator selected next step: %s (job %s)", chosen, job.id)
        # Enqueue the chosen next step (if not deny/timeout)
        if result.get("action") == "choice":
            await notifier.send(f"⏭ Queuing next step: *{chosen}*", parse_mode="Markdown")
            # Future: enqueue follow-up skill
    else:
        log.info("suggest_next: no Telegram configured. Suggestions: %s", choices)


async def _persist_job_postgres(job: Job, findings: list[dict[str, Any]]) -> None:
    """Write job result to Postgres (best-effort, does not block job completion)."""
    if not POSTGRES_DSN:
        return

    try:
        import psycopg2
        conn = psycopg2.connect(POSTGRES_DSN)
        conn.autocommit = True
        cur = conn.cursor()

        # Upsert target
        cur.execute(
            """
            INSERT INTO targets (value, type)
            VALUES (%s, %s)
            ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
            RETURNING id
            """,
            (job.target, "domain"),
        )
        target_id = cur.fetchone()[0]

        # Insert scan
        cur.execute(
            """
            INSERT INTO scans (target_id, tool, status)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (target_id, job.skill, job.status),
        )
        scan_id = cur.fetchone()[0]

        # Insert findings
        for f in findings:
            cur.execute(
                """
                INSERT INTO vulns (scan_id, severity, title, detail)
                VALUES (%s, %s, %s, %s)
                """,
                (scan_id, f.get("severity"), f.get("title"), json.dumps(f)),
            )

        conn.close()
        log.debug("Persisted job %s to Postgres (scan_id=%s)", job.id, scan_id)
    except Exception as exc:
        log.debug("Postgres persist skipped: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Job queue + scheduling
# ─────────────────────────────────────────────────────────────────────────────

class Daemon:
    """
    Main daemon controller. Owns the job queue and the worker pool.
    """

    def __init__(self, dry_run: bool = False, once: bool = False) -> None:
        self.dry_run = dry_run
        self.once = once
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._active_jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        self._notifier: Notifier | None = None
        self._bot_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ── Public API (telegram.py calls these) ─────────────────────────────

    async def enqueue(self, skill: str, params: dict[str, Any]) -> str:
        """Add a new job to the queue. Returns job ID."""
        job = Job(skill=skill, params=params)
        self._active_jobs[job.id] = job
        await self._queue.put(job)
        log.info("Enqueued job %s: skill=%s target=%s", job.id, skill, params.get("target"))
        return job.id

    def get_status(self) -> list[dict[str, Any]]:
        """Return current snapshot of all tracked jobs."""
        return [j.to_dict() for j in self._active_jobs.values()]

    # ── Startup ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialise connections, register callbacks, launch background tasks."""
        log.info("═══════════════════════════════════")
        log.info("  HexClaw Daemon starting up")
        log.info("  DRY RUN: %s  |  ONCE: %s", self.dry_run, self.once)
        log.info("═══════════════════════════════════")

        # Register callbacks so telegram.py can enqueue jobs
        register_enqueue(self.enqueue)
        register_status(self.get_status)

        # Init notifier
        if BOT_TOKEN and TELEGRAM_CHAT_ID:
            self._notifier = Notifier(BOT_TOKEN, TELEGRAM_CHAT_ID)
        else:
            log.warning("Telegram not configured — notifications disabled")

        # Start Telegram bot in background task
        self._bot_task = asyncio.create_task(
            self._run_telegram(), name="hexclaw.telegram"
        )

        # Notify operator the daemon came online
        if self._notifier:
            await self._notifier.send(
                "🦾 *HexClaw daemon online*\n"
                f"Mode: {'dry-run' if self.dry_run else 'live'}\n"
                "Use /recon <target> to start scanning."
            )

    # ── Main heartbeat loop ───────────────────────────────────────────────

    async def run(self) -> None:
        """Main event loop: drain queue → sleep → repeat."""
        await self.start()

        try:
            while not self._stop_event.is_set():
                await self._drain_queue()

                if self.once and self._queue.empty():
                    log.info("--once flag: queue empty, exiting.")
                    break

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=HEARTBEAT_SEC,
                    )
                except asyncio.TimeoutError:
                    pass  # Normal heartbeat tick

        except asyncio.CancelledError:
            log.info("Daemon run loop cancelled.")
        finally:
            await self.shutdown()

    async def _drain_queue(self) -> None:
        """Spawn worker tasks for all jobs currently in the queue."""
        while not self._queue.empty():
            try:
                job = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            task = asyncio.create_task(
                self._run_job(job),
                name=f"job.{job.id}",
            )
            task.add_done_callback(lambda t: self._job_done_callback(t))

    async def _run_job(self, job: Job) -> None:
        """Worker: acquire semaphore and run the skill."""
        async with self._semaphore:
            notifier = self._notifier or _NullNotifier()  # type: ignore
            try:
                await run_skill(job, notifier, dry_run=self.dry_run)
            except Exception as exc:
                log.exception("Unhandled error in job %s", job.id)
                job.status = JobStatus.FAILED
                job.error = str(exc)
                await notifier.send(f"💥 Job `{job.id}` crashed: `{exc}`")

    def _job_done_callback(self, task: asyncio.Task) -> None:
        if task.exception():
            log.error("Job task exception: %s", task.exception())

    async def _run_telegram(self) -> None:
        """Launch the Telegram bot long-polling loop."""
        try:
            await tg_module.run_bot_async()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("Telegram bot crashed: %s", exc)

    # ── Shutdown ──────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        log.info("Shutting down daemon...")
        self._stop_event.set()

        if self._bot_task and not self._bot_task.done():
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass

        if self._notifier:
            try:
                await self._notifier.send("🛑 *HexClaw daemon offline.*")
            except Exception:
                pass

        log.info("HexClaw daemon stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Null notifier (when Telegram not configured)
# ─────────────────────────────────────────────────────────────────────────────

class _NullNotifier:
    async def send(self, text: str, **kwargs) -> None:
        log.info("[NOTIFY] %s", text[:120])

    async def send_report(self, **kwargs) -> None:
        log.info("[NOTIFY] Report: job=%s target=%s findings=%d",
                 kwargs.get("job_id"), kwargs.get("target"), len(kwargs.get("findings", [])))

    async def send_alert(self, **kwargs) -> None:
        log.info("[NOTIFY] Alert: %s", kwargs.get("title"))

    async def request_approval(self, **kwargs) -> dict:
        log.info("[NOTIFY] Approval requested (auto-approve, no Telegram): %s", kwargs.get("approval_id"))
        return {"action": "approve", "choice": None}


# ─────────────────────────────────────────────────────────────────────────────
# Signal handling
# ─────────────────────────────────────────────────────────────────────────────

def _install_signal_handlers(daemon: Daemon, loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGINT / SIGTERM for graceful shutdown (Linux/macOS only)."""
    if sys.platform == "win32":
        # Windows: KeyboardInterrupt raised normally by asyncio
        return

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.ensure_future(daemon.shutdown(), loop=loop),
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="HexClaw daemon — autonomous cybersecurity agent")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse skills and log tool calls without executing them against MCP",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Drain queue once and exit (useful for one-shot CI invocation)",
    )
    parser.add_argument(
        "--enqueue",
        metavar="SKILL:TARGET",
        help="Seed the queue with one job before starting, e.g. recon_osint:example.com",
    )
    args = parser.parse_args()

    daemon = Daemon(dry_run=args.dry_run, once=args.once)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(daemon, loop)

    # Pre-seed queue if --enqueue passed
    if args.enqueue:
        if ":" not in args.enqueue:
            print("ERROR: --enqueue format is SKILL:TARGET, e.g. recon_osint:example.com")
            sys.exit(1)
        skill, target = args.enqueue.split(":", 1)
        loop.run_until_complete(daemon.enqueue(skill, {"target": target}))
        log.info("Pre-seeded queue: skill=%s target=%s", skill, target)

    try:
        loop.run_until_complete(daemon.run())
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received — shutting down")
        loop.run_until_complete(daemon.shutdown())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
