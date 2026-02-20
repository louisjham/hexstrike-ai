"""
HexClaw — monitor.py
====================
Continuous threat intelligence monitor. Polls RSS/CVE feeds and Shodan
real-time alerts, deduplicates, severity-scores, and pushes Telegram
notifications for findings that match monitored keywords/targets.

PRD requirements:
  • RSS/CVE feed parsing        — feedparser, async polling
  • Shodan real-time alerts     — Shodan Monitor API (if key provided)
  • Deduplication               — fingerprint hash stored in set (+ Redis if available)
  • Severity scoring            — keyword-based CVSS approximation
  • Telegram delivery           — via Notifier; respects TELEGRAM_CHAT_ID whitelist
  • Postgres write-back         — alert stored in alerts table (best-effort)
  • 0 inference for delivery    — LLM only called to *summarise* high-severity CVEs
                                  (tier=free, result cached forever)

Run modes:
  python monitor.py              # run forever (poll every MONITOR_INTERVAL_SEC)
  python monitor.py --once       # one pass then exit (useful for cron)
  python monitor.py --dry-run    # log alerts but don't send Telegram or write DB
  python monitor.py --test-feed  # force-fire a test alert

Integration with daemon.py:
  from monitor import Monitor
  monitor = Monitor(notifier=daemon.notifier)
  asyncio.create_task(monitor.run())
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("hexclaw.monitor")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

from config import LOG_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "monitor.log", encoding="utf-8"),
    ],
)

# Feed URLs — comma-separated list from .env, with sensible defaults
_DEFAULT_FEEDS = ",".join([
    "https://feeds.feedburner.com/TheHackersNews",
    "https://www.bleepingcomputer.com/feed/",
    "https://www.cisa.gov/cybersecurity-advisories/all.xml",
    "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
    "https://www.exploit-db.com/rss.xml",
])
RSS_FEEDS: list[str] = [
    u.strip()
    for u in os.getenv("RSS_FEEDS", _DEFAULT_FEEDS).split(",")
    if u.strip()
]

SHODAN_API_KEY: str = os.getenv("SHODAN_API_KEY", "")
TELEGRAM_CHAT_ID: int = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
POSTGRES_DSN: str = os.getenv("POSTGRES_DSN", "")
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

MONITOR_INTERVAL_SEC: int = int(os.getenv("MONITOR_INTERVAL_SEC", "900"))   # 15 min
ALERT_MIN_SEVERITY: str = os.getenv("ALERT_MIN_SEVERITY", "medium")         # minimum to alert
SHODAN_MONITOR_INTERVAL: int = int(os.getenv("SHODAN_MONITOR_INTERVAL", "3600"))  # 1 hr

# Keywords that elevate severity (matched against title + summary)
_CRITICAL_KEYWORDS = [
    "remote code execution", "rce", "zero-day", "0day", "critical",
    "unauthenticated", "log4shell", "log4j", "spring4shell", "proxylogon",
    "proxyshell", "printnightmare", "eternalblue", "bluekeep",
]
_HIGH_KEYWORDS = [
    "authentication bypass", "privilege escalation", "sql injection", "sqli",
    "path traversal", "lfi", "rfi", "xxe", "deserialization",
    "heap overflow", "buffer overflow", "use-after-free",
]
_MEDIUM_KEYWORDS = [
    "xss", "cross-site scripting", "csrf", "ssrf", "open redirect",
    "information disclosure", "sensitive data", "default credentials",
]

# CVSS score thresholds → severity labels
_CVSS_SEVERITY: list[tuple[float, str]] = [
    (9.0, "critical"),
    (7.0, "high"),
    (4.0, "medium"),
    (0.1, "low"),
]

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
_SEVERITY_EMOJI = {
    "critical": "[CRITICAL]",
    "high":     "[HIGH]",
    "medium":   "[MEDIUM]",
    "low":      "[LOW]",
    "info":     "[INFO]",
}


# ─────────────────────────────────────────────────────────────────────────────
# Alert data class
# ─────────────────────────────────────────────────────────────────────────────

class Alert:
    """Normalised alert from any source (RSS, Shodan, manual)."""

    __slots__ = ("source", "title", "url", "summary", "severity", "published", "fingerprint")

    def __init__(
        self,
        source: str,
        title: str,
        url: str,
        summary: str = "",
        severity: str = "info",
        published: str = "",
    ) -> None:
        self.source = source
        self.title = title[:500]
        self.url = url
        self.summary = summary[:2000]
        self.severity = severity
        self.published = published
        self.fingerprint = self._fingerprint()

    def _fingerprint(self) -> str:
        """SHA-256 of source+URL+title — used for deduplication."""
        raw = f"{self.source}:{self.url}:{self.title}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def format_telegram(self, summary: str | None = None) -> str:
        """Format alert for Telegram Markdown message."""
        emoji = _SEVERITY_EMOJI.get(self.severity, "\u26aa")
        lines = [
            f"{emoji} *[{self.severity.upper()}]* {self.title}",
            f"Source: `{self.source}`",
        ]
        if self.published:
            lines.append(f"Published: {self.published}")
        if summary:
            lines.append(f"\n_{summary}_")
        if self.url:
            lines.append(f"\n[Read more]({self.url})")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source":      self.source,
            "title":       self.title,
            "url":         self.url,
            "severity":    self.severity,
            "published":   self.published,
            "fingerprint": self.fingerprint,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Severity scorer
# ─────────────────────────────────────────────────────────────────────────────

def _score_severity(title: str, summary: str, cvss: float | None = None) -> str:
    """
    Derive a severity label from CVSS score (if available) or keyword matching.
    Returns: "critical" | "high" | "medium" | "low" | "info"
    """
    if cvss is not None:
        for threshold, label in _CVSS_SEVERITY:
            if cvss >= threshold:
                return label
        return "info"

    text = (title + " " + summary).lower()
    for kw in _CRITICAL_KEYWORDS:
        if kw in text:
            return "critical"
    for kw in _HIGH_KEYWORDS:
        if kw in text:
            return "high"
    for kw in _MEDIUM_KEYWORDS:
        if kw in text:
            return "medium"

    # Heuristic: "CVE-YYYY-NNNNN" mentioned
    if re.search(r"cve-\d{4}-\d+", text):
        return "low"

    return "info"


def _min_severity_met(severity: str, minimum: str) -> bool:
    """Return True if severity >= minimum in our ordering."""
    try:
        return _SEVERITY_ORDER.index(severity) <= _SEVERITY_ORDER.index(minimum)
    except ValueError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication store
# ─────────────────────────────────────────────────────────────────────────────

class DedupeStore:
    """
    In-memory seen-fingerprint set with optional Redis persistence.
    Redis key: "monitor:seen:{fingerprint}"  TTL: 7 days.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._redis = self._try_redis()

    @staticmethod
    def _try_redis():
        try:
            import redis as redis_lib
            from urllib.parse import urlparse
            parsed = urlparse(REDIS_URL)
            db = int(parsed.path.lstrip("/")) if parsed.path.lstrip("/") else 2
            r = redis_lib.Redis(
                host=parsed.hostname or "localhost",
                port=parsed.port or 6379,
                db=db,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            r.ping()
            return r
        except Exception:
            return None

    def is_seen(self, fingerprint: str) -> bool:
        if fingerprint in self._seen:
            return True
        if self._redis:
            try:
                return bool(self._redis.exists(f"monitor:seen:{fingerprint}"))
            except Exception:
                pass
        return False

    def mark_seen(self, fingerprint: str) -> None:
        self._seen.add(fingerprint)
        if self._redis:
            try:
                self._redis.setex(f"monitor:seen:{fingerprint}", 604_800, "1")
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Postgres writer
# ─────────────────────────────────────────────────────────────────────────────

def _pg_write_alert(alert: Alert) -> int:
    """Write alert to Postgres alerts table. Returns alert ID or -1."""
    if not POSTGRES_DSN:
        return -1
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(POSTGRES_DSN)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts (source, title, url, severity)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (alert.source, alert.title, alert.url, alert.severity),
            )
            aid = cur.fetchone()[0]
        conn.close()
        return aid
    except Exception as exc:
        log.debug("pg_write_alert failed: %s", exc)
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# RSS feed parser
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_feed(url: str) -> list[Alert]:
    """
    Fetch and parse a single RSS/Atom feed.
    Returns a list of Alert objects.
    """
    try:
        import feedparser  # type: ignore
    except ImportError:
        log.warning("feedparser not installed — `pip install feedparser`")
        return []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "HexClaw/1.0 (+https://github.com/hexstrike-ai)"})
            content = resp.text
    except Exception as exc:
        log.warning("Failed to fetch feed %s: %s", url, exc)
        return []

    try:
        feed = feedparser.parse(content)
    except Exception as exc:
        log.warning("Failed to parse feed %s: %s", url, exc)
        return []

    source = feed.feed.get("title", url)[:50]
    alerts: list[Alert] = []

    for entry in feed.entries[:50]:  # cap at 50 entries per fetch
        title   = entry.get("title", "").strip()
        link    = entry.get("link", "")
        summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:800]  # strip HTML tags
        published = entry.get("published", "")

        if not title:
            continue

        # Extract CVSS score from summary/tags if available
        cvss = None
        cvss_match = re.search(r"cvss[^\d]*(\d+\.?\d*)", (title + summary).lower())
        if cvss_match:
            try:
                cvss = float(cvss_match.group(1))
            except ValueError:
                pass

        severity = _score_severity(title, summary, cvss)

        alerts.append(Alert(
            source=source,
            title=title,
            url=link,
            summary=summary,
            severity=severity,
            published=published,
        ))

    log.debug("Feed %s: %d entries parsed", url, len(alerts))
    return alerts


async def poll_rss_feeds() -> list[Alert]:
    """Poll all configured RSS feeds concurrently. Returns deduplicated list."""
    tasks = [_fetch_feed(url) for url in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    alerts: list[Alert] = []
    for r in results:
        if isinstance(r, list):
            alerts.extend(r)
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Shodan Monitor API
# ─────────────────────────────────────────────────────────────────────────────

async def poll_shodan_alerts() -> list[Alert]:
    """
    Fetch triggered Shodan Monitor alerts via the Shodan API.
    Requires SHODAN_API_KEY in .env.
    Returns list of Alert objects (empty if no key or API error).

    Shodan Monitor API docs:
      GET https://api.shodan.io/shodan/alert/info?key=KEY
      GET https://api.shodan.io/shodan/alert/{alert_id}/notifs?key=KEY
    """
    if not SHODAN_API_KEY:
        return []

    alerts: list[Alert] = []
    try:
        import httpx
        base = "https://api.shodan.io"
        async with httpx.AsyncClient(timeout=30.0) as client:

            # 1. List all defined monitor alerts
            resp = await client.get(f"{base}/shodan/alert/info", params={"key": SHODAN_API_KEY})
            if resp.status_code != 200:
                log.warning("Shodan alert info HTTP %s", resp.status_code)
                return []

            raw = resp.json()
            if raw is None:
                return []
            monitor_list = raw if isinstance(raw, list) else [raw]

            for monitor in monitor_list:
                alert_id = monitor.get("id", "")
                monitor_name = monitor.get("name", alert_id)
                matches = monitor.get("matches", [])

                for match in matches[:20]:
                    ip     = match.get("ip_str", "")
                    port   = match.get("port", "")
                    banner = str(match.get("data", ""))[:400]
                    cpes   = match.get("cpe", [])
                    vulns  = match.get("vulns", {})

                    # Score severity from vuln CVSSv3 if available
                    max_cvss: float | None = None
                    for cve_id, cve_data in vulns.items():
                        cvss_val = cve_data.get("cvss", 0.0)
                        if cvss_val and (max_cvss is None or cvss_val > max_cvss):
                            max_cvss = float(cvss_val)

                    severity = _score_severity(banner, str(cpes), max_cvss)

                    title = (
                        f"Shodan: {monitor_name} — {ip}:{port}"
                        + (f" ({', '.join(list(vulns.keys())[:3])})" if vulns else "")
                    )
                    alerts.append(Alert(
                        source="shodan",
                        title=title,
                        url=f"https://www.shodan.io/host/{ip}",
                        summary=banner,
                        severity=severity,
                        published=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    ))

    except Exception as exc:
        log.warning("Shodan poll failed: %s", exc)

    log.debug("Shodan: %d alerts fetched", len(alerts))
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Optional LLM summarisation (free tier, cached forever)
# ─────────────────────────────────────────────────────────────────────────────

async def _summarise_alert(alert: Alert) -> str | None:
    """
    Generate a 1-sentence LLM summary for critical/high alerts.

    PRD rule: inference only when severity=critical or high AND no cached hit.
    Uses tier=free (0 cost for free providers).
    Result cached — identical future alerts cost 0 tokens.
    """
    if alert.severity not in ("critical", "high"):
        return None

    try:
        import cache as cache_module
        import inference

        prompt = (
            f"Summarise this security alert in ONE sentence for a penetration tester:\n"
            f"Title: {alert.title}\nDetails: {alert.summary[:500]}"
        )

        # Cache check first (0 tokens on hit)
        cached = cache_module.check(prompt)
        if cached:
            return cached

        # Free-tier LLM call (low cost, may be rate-limited)
        summary = await inference.ask(
            prompt=prompt,
            complexity="low",
            system="You are a concise security alert summariser. Respond with ONE sentence only.",
        )
        return summary.strip()

    except Exception as exc:
        log.debug("Alert summarisation failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Monitor class
# ─────────────────────────────────────────────────────────────────────────────

class Monitor:
    """
    Continuous threat intelligence monitor.

    Usage:
        monitor = Monitor(notifier=daemon_notifier)
        await monitor.run()                 # forever
        await monitor.run_once()            # single pass
    """

    def __init__(
        self,
        notifier=None,
        dry_run: bool = False,
        min_severity: str = ALERT_MIN_SEVERITY,
    ) -> None:
        self._notifier = notifier
        self._dry_run = dry_run
        self._min_severity = min_severity
        self._dedupe = DedupeStore()
        self._stop_event = asyncio.Event()
        self._stats: dict[str, int] = {
            "feeds_polled": 0,
            "alerts_new": 0,
            "alerts_sent": 0,
            "alerts_skipped_severity": 0,
            "alerts_skipped_dedup": 0,
        }

    # ── Public API ────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Poll feeds in a loop until stopped."""
        log.info("Monitor starting (interval=%ds, min_severity=%s)", MONITOR_INTERVAL_SEC, self._min_severity)
        while not self._stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=MONITOR_INTERVAL_SEC)
            except asyncio.TimeoutError:
                pass
        log.info("Monitor stopped.")

    async def run_once(self) -> list[Alert]:
        """
        Single poll pass: fetch all feeds + Shodan, filter, dedupe, notify.
        Returns list of alerts that were sent.
        """
        log.debug("Monitor: polling feeds...")
        self._stats["feeds_polled"] += 1

        # Concurrent fetch
        rss_task    = asyncio.create_task(poll_rss_feeds())
        shodan_task = asyncio.create_task(poll_shodan_alerts())

        rss_alerts, shodan_alerts = await asyncio.gather(rss_task, shodan_task)
        all_alerts: list[Alert] = rss_alerts + shodan_alerts

        sent: list[Alert] = []
        for alert in all_alerts:
            action = await self._process_alert(alert)
            if action == "sent":
                sent.append(alert)

        log.info(
            "Monitor pass complete: %d total, %d sent, %d dedup-skipped, %d below-threshold",
            len(all_alerts),
            self._stats["alerts_sent"],
            self._stats["alerts_skipped_dedup"],
            self._stats["alerts_skipped_severity"],
        )
        return sent

    def stop(self) -> None:
        """Signal the monitor loop to stop after the current pass."""
        self._stop_event.set()

    def stats(self) -> dict[str, int]:
        """Return monitoring statistics."""
        return dict(self._stats)

    # ── Internal ──────────────────────────────────────────────────────────

    async def _process_alert(self, alert: Alert) -> str:
        """
        Filter, deduplicate, and dispatch a single alert.
        Returns "sent" | "dedup" | "severity" | "error"
        """

        # 1. Severity gate
        if not _min_severity_met(alert.severity, self._min_severity):
            self._stats["alerts_skipped_severity"] += 1
            return "severity"

        # 2. Deduplication
        if self._dedupe.is_seen(alert.fingerprint):
            self._stats["alerts_skipped_dedup"] += 1
            return "dedup"

        self._stats["alerts_new"] += 1
        self._dedupe.mark_seen(alert.fingerprint)

        # 3. Optional LLM summary (critical/high only, free tier, cached)
        ai_summary = await _summarise_alert(alert)

        # 4. Send Telegram notification
        if not self._dry_run:
            await self._send_telegram(alert, ai_summary)
            _pg_write_alert(alert)
        else:
            log.info("[DRY RUN] Would send alert: [%s] %s", alert.severity, alert.title)

        self._stats["alerts_sent"] += 1
        return "sent"

    async def _send_telegram(self, alert: Alert, summary: str | None = None) -> None:
        """Send formatted alert to Telegram operator chat."""
        if self._notifier is None:
            log.info("Alert (no notifier): [%s] %s", alert.severity, alert.title)
            return

        try:
            message = alert.format_telegram(summary=summary)
            await self._notifier.send(message, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as exc:
            log.warning("Failed to send alert via Telegram: %s", exc)

    async def send_test_alert(self) -> None:
        """Fire a synthetic test alert to verify the pipeline end-to-end."""
        alert = Alert(
            source="hexclaw_test",
            title="[TEST] HexClaw monitor integration check",
            url="https://github.com/hexstrike-ai",
            summary="This is a synthetic test alert to verify the monitor→Telegram pipeline.",
            severity="info",
            published=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )
        log.info("Sending test alert...")
        await self._send_telegram(alert, summary=None)
        log.info("Test alert sent.")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

_monitor_instance: Monitor | None = None


def get_monitor(notifier=None) -> Monitor:
    """Return the process-wide Monitor singleton."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = Monitor(notifier=notifier)
    return _monitor_instance


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, json as _json

    parser = argparse.ArgumentParser(description="HexClaw monitor — threat intelligence feed poller")
    parser.add_argument("--once",       action="store_true", help="Poll once then exit")
    parser.add_argument("--dry-run",    action="store_true", help="Log alerts but don't send Telegram or write DB")
    parser.add_argument("--test-alert", action="store_true", help="Fire a test alert and exit")
    parser.add_argument("--severity",   default=ALERT_MIN_SEVERITY, help="Minimum severity to alert (default: medium)")
    parser.add_argument("--stats",      action="store_true", help="Print run stats and exit")
    args = parser.parse_args()

    # Build a simple stub notifier for standalone mode
    class _CliNotifier:
        async def send(self, text: str, **kwargs) -> None:
            print("\n--- ALERT ---")
            print(text)
            print("-------------")

    notifier = _CliNotifier() if not args.dry_run else None
    monitor = Monitor(notifier=notifier, dry_run=args.dry_run, min_severity=args.severity)

    async def _main():
        if args.test_alert:
            await monitor.send_test_alert()
        elif args.once:
            sent = await monitor.run_once()
            print(f"\nSent {len(sent)} alert(s)")
            if args.stats:
                print(_json.dumps(monitor.stats(), indent=2))
        else:
            print(f"Monitor running (interval={MONITOR_INTERVAL_SEC}s, min_severity={args.severity})")
            print("Press Ctrl+C to stop\n")
            try:
                await monitor.run()
            except KeyboardInterrupt:
                monitor.stop()
                print("\nMonitor stopped.")
            if args.stats:
                print(_json.dumps(monitor.stats(), indent=2))

    asyncio.run(_main())
