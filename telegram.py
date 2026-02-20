"""
HexClaw — telegram.py
=====================
Telegram bot hub for the HexClaw autonomous agent.

Responsibilities:
  • /recon <target>    → enqueue recon_osint skill chain
  • /status            → list running / queued jobs
  • /stats             → inference usage dashboard (0 tokens — SQL only)
  • /cancel <job_id>   → mark job cancelled
  • /help              → show all commands

  • Inline approval buttons  → 0-inference human-in-the-loop
  • Multi-choice keyboards   → let operator pick next action

Bot lifecycle:
  telegram.py is started inside daemon.py in a background asyncio task.
  It can also be run standalone: python telegram.py

Environment variables (from .env):
  TELEGRAM_BOT_TOKEN  — BotFather token
  TELEGRAM_CHAT_ID    — operator chat / group ID (whitelist)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

from dotenv import load_dotenv

# ── Optional runtime imports (graceful if deps not yet installed) ─────────────
try:
    from telegram import (
        Bot,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Update,
    )
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

load_dotenv()

log = logging.getLogger("hexclaw.telegram")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_ID: int | None = int(os.getenv("TELEGRAM_CHAT_ID", "0")) or None

# Filled in by daemon.py when it starts, so telegram.py can enqueue work
_enqueue_callback: Callable[[str, dict[str, Any]], Coroutine] | None = None
_status_callback: Callable[[], list[dict[str, Any]]] | None = None
_orchestrate_callback: Callable[[str], Coroutine] | None = None

# Pending approval gates: approval_id → asyncio.Future
_pending_approvals: dict[str, asyncio.Future] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Registration helpers (called by daemon.py at startup)
# ─────────────────────────────────────────────────────────────────────────────

def register_enqueue(fn: Callable) -> None:
    """Register the daemon's enqueue coroutine so /recon can submit jobs."""
    global _enqueue_callback
    _enqueue_callback = fn


def register_status(fn: Callable) -> None:
    """Register the daemon's status getter so /status can query jobs."""
    global _status_callback
    _status_callback = fn


def register_orchestrate(fn: Callable) -> None:
    """Register the daemon's orchestrate coroutine."""
    global _orchestrate_callback
    _orchestrate_callback = fn


# ─────────────────────────────────────────────────────────────────────────────
# Auth guard
# ─────────────────────────────────────────────────────────────────────────────

def _is_allowed(update: Update) -> bool:
    if ALLOWED_CHAT_ID is None:
        return True  # No restriction set
    chat_id = (
        update.effective_chat.id
        if update.effective_chat
        else update.effective_user.id
    )
    return chat_id == ALLOWED_CHAT_ID


async def _unauthorized(update: Update) -> None:
    if update.message:
        await update.message.reply_text("⛔ Unauthorized.")
    log.warning("Unauthorized access attempt from chat %s", update.effective_chat)


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _unauthorized(update)

    text = (
        "🦾 *HexClaw Commands*\n\n"
        "`/orchestrate <goal>` — Orchestrate a multi-step workflow via goal\n"
        "`/edit <workflow>` — View/edit workflow YAML (v2 placeholder)\n"
        "`/recon <target>` — Run full recon chain (amass→rustscan→nuclei)\n"
        "`/status` — List running / queued jobs\n"
        "`/stats` — Inference usage dashboard\n"
        "`/cancel <job_id>` — Cancel a queued job\n"
        "`/help` — Show this message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_recon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _unauthorized(update)

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/recon <target>`\nExample: `/recon example.com`",
            parse_mode="Markdown",
        )
        return

    target = args[0].strip()
    msg = await update.message.reply_text(
        f"🔍 Queuing recon for `{target}`...", parse_mode="Markdown"
    )

    if _enqueue_callback is None:
        await msg.edit_text("❌ Daemon not connected. Is daemon.py running?")
        return

    try:
        job_id = await _enqueue_callback("recon_osint", {"target": target})
        await msg.edit_text(
            f"✅ Job `{job_id}` queued for *{target}*\n"
            f"Use /status to track progress.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        log.exception("Enqueue failed")
        await msg.edit_text(f"❌ Failed to enqueue: {exc}")


async def cmd_orchestrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _unauthorized(update)

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/orchestrate <goal>`\nExample: `/orchestrate \"scan example.com for vulns\"`",
            parse_mode="Markdown",
        )
        return

    goal = " ".join(args).strip()
    msg = await update.message.reply_text(
        f"🤖 Planning orchestration for goal: *{goal}*...", parse_mode="Markdown"
    )

    if _orchestrate_callback is None:
        await msg.edit_text("❌ Daemon not connected. Is daemon.py running?")
        return

    try:
        job_id = await _orchestrate_callback(goal)
        await msg.edit_text(
            f"✅ Orchestration started. Job `{job_id}` queued.\n"
            f"Use /status to track progress.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        log.exception("Orchestrate failed")
        await msg.edit_text(f"❌ Failed to orchestrate: {exc}")


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _unauthorized(update)

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/edit <workflow_name>`", parse_mode="Markdown")
        return

    workflow = args[0].strip()
    await update.message.reply_text(
        f"📝 *YAML Editor (v2)*\nReading `{workflow}.yaml`...\n\n_Note: Inline editing coming in v2.1._",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _unauthorized(update)

    if _status_callback is None:
        await update.message.reply_text("❌ Daemon not connected.")
        return

    try:
        jobs = _status_callback()
    except Exception as exc:
        await update.message.reply_text(f"❌ Error fetching status: {exc}")
        return

    if not jobs:
        await update.message.reply_text("📭 No active jobs.")
        return

    lines = ["📋 *Active Jobs*\n"]
    icons = {
        "pending": "⏳",
        "running": "🔄",
        "done": "✅",
        "failed": "❌",
        "cancelled": "🚫",
    }
    for job in jobs[:20]:  # cap at 20 to avoid message length limit
        icon = icons.get(job.get("status", ""), "❓")
        jid = job.get("id", "?")
        skill = job.get("skill", "?")
        target = job.get("target", "?")
        status = job.get("status", "?")
        elapsed = job.get("elapsed_sec")
        elapsed_str = f" ({elapsed}s)" if elapsed else ""
        lines.append(f"{icon} `{jid}` *{skill}* → `{target}` [{status}]{elapsed_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zero-inference stats — reads SQLite token log directly."""
    if not _is_allowed(update):
        return await _unauthorized(update)

    import sqlite3

    db_path = ROOT / "data" / "token_log.db"
    if not db_path.exists():
        await update.message.reply_text("📊 No token log found yet.")
        return

    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT
                provider,
                model,
                COUNT(*)        AS calls,
                SUM(tokens_in)  AS tok_in,
                SUM(tokens_out) AS tok_out,
                SUM(cost_usd)   AS cost,
                SUM(cache_hit)  AS cache_hits
            FROM token_log
            GROUP BY provider, model
            ORDER BY cost DESC
        """).fetchall()

        totals = conn.execute("""
            SELECT
                COUNT(*)        AS calls,
                SUM(tokens_in)  AS tok_in,
                SUM(tokens_out) AS tok_out,
                SUM(cost_usd)   AS cost,
                SUM(cache_hit)  AS cache_hits
            FROM token_log
        """).fetchone()
        conn.close()
    except Exception as exc:
        await update.message.reply_text(f"❌ DB error: {exc}")
        return

    lines = ["📊 *Inference Usage Dashboard*\n"]
    for row in rows[:10]:
        provider, model, calls, tok_in, tok_out, cost, cache_hits = row
        cost_str = f"${cost:.4f}" if cost else "$0.0000"
        lines.append(
            f"• `{model}` ({provider})\n"
            f"  {calls} calls · {tok_in or 0}↑ {tok_out or 0}↓ tokens · "
            f"{cost_str} · {cache_hits or 0} cache hits"
        )

    if totals:
        calls, tok_in, tok_out, cost, cache_hits = totals
        cost_str = f"${cost:.4f}" if cost else "$0.0000"
        lines.append(
            f"\n*Totals*: {calls} calls · "
            f"{tok_in or 0}↑ {tok_out or 0}↓ tokens · "
            f"{cost_str} · {cache_hits or 0} cache hits"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _unauthorized(update)

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/cancel <job_id>`", parse_mode="Markdown")
        return

    job_id = args[0].strip()
    # Signal daemon via the status callback's cancel mechanism (set job cancelled in DB)
    # For now, we emit a sentinel to the pending approvals map
    future = _pending_approvals.get(f"cancel:{job_id}")
    if future and not future.done():
        future.set_result({"action": "cancel"})
        await update.message.reply_text(f"🚫 Cancellation signal sent for `{job_id}`.", parse_mode="Markdown")
    else:
        # Emit via global cancellation set (daemon polls this)
        _cancelled_jobs.add(job_id)
        await update.message.reply_text(
            f"🚫 Job `{job_id}` marked for cancellation.", parse_mode="Markdown"
        )


# Global set that daemon.py polls to cancel jobs
_cancelled_jobs: set[str] = set()


def is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled_jobs


def clear_cancel(job_id: str) -> None:
    _cancelled_jobs.discard(job_id)


# ─────────────────────────────────────────────────────────────────────────────
# Inline approval gates (human-in-the-loop, 0 inference)
# ─────────────────────────────────────────────────────────────────────────────

async def request_approval(
    bot: "Bot",
    chat_id: int,
    approval_id: str,
    prompt: str,
    choices: list[str] | None = None,
    timeout_sec: int = 300,
) -> dict[str, Any]:
    """
    Send an inline keyboard to the operator and wait for a response.

    Args:
        bot:         Telegram Bot instance
        chat_id:     Operator chat ID
        approval_id: Unique ID for this approval gate
        prompt:      Message text shown to operator
        choices:     If given, show these as multi-choice buttons.
                     If None, shows [✅ Approve] [❌ Deny] only.
        timeout_sec: How long to wait before auto-denying

    Returns:
        dict with keys: action (str), choice (str|None)
    """
    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()
    _pending_approvals[approval_id] = future

    if choices:
        buttons = [
            [InlineKeyboardButton(c, callback_data=f"choice:{approval_id}:{c}")]
            for c in choices
        ]
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"deny:{approval_id}")])
    else:
        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{approval_id}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny:{approval_id}"),
        ]]

    keyboard = InlineKeyboardMarkup(buttons)
    await bot.send_message(
        chat_id=chat_id,
        text=prompt,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    try:
        result = await asyncio.wait_for(future, timeout=timeout_sec)
    except asyncio.TimeoutError:
        result = {"action": "timeout", "choice": None}
        log.warning("Approval gate %s timed out after %ss", approval_id, timeout_sec)
    finally:
        _pending_approvals.pop(approval_id, None)

    return result


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resolve pending approval futures when operator presses an inline button."""
    query = update.callback_query
    await query.answer()

    data: str = query.data or ""
    parts = data.split(":", 2)

    if not parts:
        return

    action = parts[0]

    if action == "approve" and len(parts) >= 2:
        approval_id = parts[1]
        future = _pending_approvals.get(approval_id)
        if future and not future.done():
            future.set_result({"action": "approve", "choice": None})
        await query.edit_message_text("✅ Approved.")

    elif action == "deny" and len(parts) >= 2:
        approval_id = parts[1]
        future = _pending_approvals.get(approval_id)
        if future and not future.done():
            future.set_result({"action": "deny", "choice": None})
        await query.edit_message_text("❌ Denied.")

    elif action == "choice" and len(parts) >= 3:
        approval_id = parts[1]
        choice = parts[2]
        future = _pending_approvals.get(approval_id)
        if future and not future.done():
            future.set_result({"action": "choice", "choice": choice})
        await query.edit_message_text(f"✅ Selected: *{choice}*", parse_mode="Markdown")

    else:
        log.warning("Unknown callback data: %s", data)


# ─────────────────────────────────────────────────────────────────────────────
# Outbound notification helpers (called by daemon.py)
# ─────────────────────────────────────────────────────────────────────────────

class Notifier:
    """
    Simple async helper for daemon.py to send messages without holding
    a full Application reference.

    Usage:
        notifier = Notifier(bot_token, chat_id)
        await notifier.send("💥 Scan complete!")
        await notifier.send_report(job_id, target, findings)
    """

    def __init__(self, token: str, chat_id: int) -> None:
        self._token = token
        self._chat_id = chat_id
        self._bot: "Bot | None" = None

    def _get_bot(self) -> "Bot":
        if self._bot is None:
            self._bot = Bot(token=self._token)
        return self._bot

    async def send(self, text: str, parse_mode: str = "Markdown") -> None:
        try:
            await self._get_bot().send_message(
                chat_id=self._chat_id,
                text=text[:4096],  # Telegram max
                parse_mode=parse_mode,
            )
        except Exception as exc:
            log.error("Telegram send failed: %s", exc)

    async def send_file(self, file_path: str, caption: str | None = None) -> None:
        """Send a document/file to the operator."""
        try:
            path = Path(file_path)
            if not path.exists():
                log.error(f"File not found for Telegram: {file_path}")
                return
            with open(path, "rb") as fh:
                await self._get_bot().send_document(
                    chat_id=self._chat_id,
                    document=fh,
                    caption=caption[:1024] if caption else None,
                )
        except Exception as exc:
            log.error(f"Telegram file send failed: {exc}")

    async def send_report(
        self,
        job_id: str,
        target: str,
        skill: str,
        findings: list[dict[str, Any]],
        top_findings: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> None:
        """
        Send a structured scan report with optional suggest_next buttons.
        0 inference — all content comes from structured scan output.
        """
        sev_counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info").lower()
            sev_counts[sev] = sev_counts.get(sev, 0) + 1

        sev_line = " · ".join(
            f"{v} {k}" for k, v in sorted(sev_counts.items(), key=lambda x: ["critical","high","medium","low","info"].index(x[0]) if x[0] in ["critical","high","medium","low","info"] else 99)
        ) or "no findings"

        lines = [
            f"🎯 *HexClaw Report* — `{target}`",
            f"Skill: `{skill}` · Job: `{job_id}`",
            f"Severity: {sev_line}",
            f"Total findings: {len(findings)}",
        ]

        if top_findings:
            lines.append("\n🔝 *Top Findings*")
            for tf in top_findings[:5]:
                lines.append(f"  • {tf}")

        if next_steps:
            lines.append("\n⏭ *Suggested Next Steps*")
            for step in next_steps[:3]:
                lines.append(f"  → {step}")

        await self.send("\n".join(lines))

    async def send_alert(
        self,
        source: str,
        title: str,
        url: str | None = None,
        severity: str = "unknown",
    ) -> None:
        """Send a CVE / RSS alert notification."""
        sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
            severity.lower(), "⚪"
        )
        lines = [
            f"{sev_icon} *{source.upper()} Alert*",
            f"*{title}*",
        ]
        if url:
            lines.append(f"[Read more]({url})")
        await self.send("\n".join(lines))

    async def request_approval(
        self,
        approval_id: str,
        prompt: str,
        choices: list[str] | None = None,
        timeout_sec: int = 300,
    ) -> dict[str, Any]:
        """Delegate to module-level request_approval."""
        return await request_approval(
            bot=self._get_bot(),
            chat_id=self._chat_id,
            approval_id=approval_id,
            prompt=prompt,
            choices=choices,
            timeout_sec=timeout_sec,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

def build_application() -> "Application":
    """Build and return the configured PTB Application (not started yet)."""
    if not TELEGRAM_AVAILABLE:
        raise ImportError("python-telegram-bot not installed. Run: pip install 'python-telegram-bot>=21.0'")

    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("orchestrate", cmd_orchestrate))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("recon", cmd_recon))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(_handle_callback))

    return app


async def run_bot_async() -> None:
    """
    Run the bot using long-polling inside the current event loop.
    Called from daemon.py as an asyncio task.
    """
    if not TELEGRAM_AVAILABLE:
        log.error("python-telegram-bot not installed — Telegram bot disabled")
        return

    if not BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return

    app = build_application()
    log.info("Starting Telegram bot (long-polling)...")

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot is running. Waiting for messages...")
        # Keep alive — daemon.py cancels this task on shutdown
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await app.updater.stop()
            await app.stop()
    log.info("Telegram bot stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Standalone entry-point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    log.info("Running telegram.py standalone...")

    if not TELEGRAM_AVAILABLE:
        print("ERROR: python-telegram-bot not installed.")
        print("Run:   pip install 'python-telegram-bot>=21.0'")
        raise SystemExit(1)

    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        raise SystemExit(1)

    asyncio.run(run_bot_async())
