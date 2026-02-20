"""
HexClaw — data.py
=================
Unified data layer for the HexClaw autonomous agent.

Three concerns, one module:

  1. DuckStore  — DuckDB over Parquet files
       • store_records()   write records to a Parquet file (append or create)
       • query_parquet()   run SQL directly over one or many Parquet files
       • merge_parquets()  union multiple Parquet files into one view
       • aggregate()       common analytics (severity counts, top hosts, …)

  2. PgStore    — PostgreSQL write-through (long-term persistence)
       • upsert_target()   idempotent target registration
       • record_scan()     create a scan row, update status
       • record_vulns()    bulk insert findings
       • get_stats()       aggregated counts for /stats Telegram command

  3. TextToSQL  — natural-language → SQL bridge
       PRD rule: SQL cache hits for analytics → 0 inference
       • answer()          check cache → run SQL → only call LLM if cache miss
       • suggest_next()    rule-based: 0 inference, derives next steps from data

Usage:
    from data import DuckStore, PgStore, TextToSQL, suggest_next_from_data

    duck = DuckStore()
    pg   = PgStore()
    t2s  = TextToSQL(duck)

    # Store nuclei output to Parquet
    duck.store_records("data/abc123/vulns.parquet", findings)

    # Query it
    rows = duck.query_parquet("data/abc123/vulns.parquet",
                              "SELECT severity, COUNT(*) AS n GROUP BY 1")

    # Aggregate across ALL job Parquets
    summary = duck.aggregate(job_id="abc123")

    # Postgres
    tid   = pg.upsert_target("example.com", "domain")
    sid   = pg.record_scan(tid, "recon_osint")
    pg.record_vulns(sid, findings)

    # Text-to-SQL (checks cache → SQL → LLM only on miss)
    answer = await t2s.answer("How many critical vulns in the last 7 days?")

    # Rule-based suggest_next (0 inference)
    steps = suggest_next_from_data(duck, job_id="abc123")
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("hexclaw.data")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"

POSTGRES_DSN: str = os.getenv("POSTGRES_DSN", "")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pg_connect():
    """Return a live psycopg2 connection or raise ImportError/OperationalError."""
    import psycopg2  # type: ignore
    if not POSTGRES_DSN:
        raise ValueError("POSTGRES_DSN not set in .env")
    return psycopg2.connect(POSTGRES_DSN)


def _flatten(record: Any) -> dict[str, Any]:
    """Ensure record is a plain dict (flatten dataclass / pydantic if needed)."""
    if isinstance(record, dict):
        return record
    if hasattr(record, "__dict__"):
        return record.__dict__
    return {"value": str(record)}


# ─────────────────────────────────────────────────────────────────────────────
# 1. DuckStore — DuckDB/Parquet analytics
# ─────────────────────────────────────────────────────────────────────────────

class DuckStore:
    """
    DuckDB-powered analytics over Parquet files.

    DuckDB is opened in-memory per call (stateless) — no persistent .db file
    needed; Parquet files on disk are the source of truth.

    All public methods return plain Python dicts / lists so callers don't
    need to import duckdb directly.
    """

    # ── Parquet write ─────────────────────────────────────────────────────

    def store_records(
        self,
        parquet_path: str | Path,
        records: list[dict[str, Any]],
        mode: str = "overwrite",
    ) -> int:
        """
        Write a list of record dicts to *parquet_path*.

        Args:
            parquet_path: Destination .parquet file path
            records:      List of dicts (all must have compatible keys)
            mode:         "overwrite" (default) or "append"

        Returns:
            Number of rows written

        Raises:
            ImportError  if duckdb not installed
            ValueError   if records is empty
        """
        if not records:
            return 0

        import duckdb  # type: ignore

        path = Path(parquet_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Normalise: ensure all records have the same keys (fill missing with None)
        all_keys: set[str] = set()
        for r in records:
            all_keys.update(_flatten(r).keys())
        keys = sorted(all_keys)

        normalised = [
            {k: _flatten(r).get(k) for k in keys}
            for r in records
        ]

        # Build an Arrow table (DuckDB ships with PyArrow) from the list of dicts
        # so we can ingest it directly without FROM ? bind syntax issues.
        try:
            import pyarrow as pa  # type: ignore

            col_data: dict[str, list] = {k: [row[k] for row in normalised] for k in keys}
            arrow_table = pa.table(col_data)
            con = duckdb.connect()
            con.register("_newdata", arrow_table)

        except ImportError:
            # Absolute fallback: write JSON lines to a temp file and read via DuckDB
            import tempfile, json as _json
            tmp_file = Path(tempfile.mktemp(suffix=".ndjson"))
            tmp_file.write_text("\n".join(_json.dumps(r) for r in normalised), encoding="utf-8")
            con = duckdb.connect()
            con.execute(f"CREATE TABLE _newdata AS SELECT * FROM read_json_auto('{tmp_file}')")
            tmp_file.unlink(missing_ok=True)

        if mode == "append" and path.exists():
            con.execute(f"CREATE TABLE _existing AS SELECT * FROM '{path}'")
            con.execute(
                f"COPY (SELECT * FROM _existing UNION ALL SELECT * FROM _newdata) "
                f"TO '{path}' (FORMAT PARQUET)"
            )
        else:
            con.execute(f"COPY (SELECT * FROM _newdata) TO '{path}' (FORMAT PARQUET)")

        count = con.execute(f"SELECT COUNT(*) FROM '{path}'").fetchone()[0]
        con.close()

        log.debug("Stored %d rows -> %s", count, path)
        return count

    # ── Parquet read / query ──────────────────────────────────────────────

    def query_parquet(
        self,
        parquet_path: str | Path,
        sql: str | None = None,
        params: list | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query a single Parquet file with optional SQL.

        If *sql* is None, returns all rows (SELECT *).
        The table is aliased as `data` inside the SQL.

        Example:
            rows = duck.query_parquet(
                "data/abc/vulns.parquet",
                "SELECT severity, COUNT(*) AS n FROM data GROUP BY 1 ORDER BY 2 DESC"
            )
        """
        import duckdb  # type: ignore

        path = Path(parquet_path)
        if not path.exists():
            log.warning("Parquet not found (returning empty): %s", path)
            return []

        con = duckdb.connect()
        con.execute(f"CREATE VIEW data AS SELECT * FROM '{path}'")

        if sql is None:
            sql = "SELECT * FROM data"

        if params:
            result = con.execute(sql, params)
        else:
            result = con.execute(sql)

        cols = [d[0] for d in result.description]
        rows = [dict(zip(cols, row)) for row in result.fetchall()]
        con.close()
        return rows

    def query_glob(
        self,
        glob_pattern: str,
        sql: str,
    ) -> list[dict[str, Any]]:
        """
        Query multiple Parquet files matched by a glob pattern.
        The union of all matched files is exposed as the `data` view.

        Example:
            # All nuclei results across all jobs
            rows = duck.query_glob(
                "data/*/vulns.parquet",
                "SELECT severity, COUNT(*) n FROM data GROUP BY 1"
            )
        """
        import duckdb  # type: ignore

        con = duckdb.connect()
        glob = str(ROOT / glob_pattern) if not glob_pattern.startswith(str(ROOT)) else glob_pattern
        con.execute(f"CREATE VIEW data AS SELECT * FROM read_parquet('{glob}')")

        try:
            result = con.execute(sql)
            cols = [d[0] for d in result.description]
            rows = [dict(zip(cols, row)) for row in result.fetchall()]
        except Exception as exc:
            log.warning("query_glob failed for '%s': %s", glob_pattern, exc)
            rows = []
        finally:
            con.close()

        return rows

    def merge_parquets(
        self,
        paths: list[str | Path],
        dest: str | Path,
    ) -> int:
        """
        Union multiple Parquet files into a single output file.
        Returns total row count.
        """
        if not paths:
            return 0

        import duckdb  # type: ignore

        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        con = duckdb.connect()
        parts = " UNION ALL ".join(
            [f"SELECT * FROM '{Path(p)}'" for p in paths if Path(p).exists()]
        )
        if not parts:
            con.close()
            return 0

        con.execute(f"COPY ({parts}) TO '{dest_path}' (FORMAT PARQUET)")
        count = con.execute(f"SELECT COUNT(*) FROM '{dest_path}'").fetchone()[0]
        con.close()
        log.debug("Merged %d rows → %s", count, dest_path)
        return count

    # ── Common aggregations ───────────────────────────────────────────────

    def aggregate(self, job_id: str) -> dict[str, Any]:
        """
        Aggregate all Parquet outputs for a single job_id.
        Returns a structured summary dict.
        """
        job_dir = DATA_DIR / job_id
        if not job_dir.exists():
            return {"job_id": job_id, "error": "job directory not found"}

        result: dict[str, Any] = {"job_id": job_id}

        # Subdomains from amass
        subs_pq = job_dir / "subs.parquet"
        if subs_pq.exists():
            rows = self.query_parquet(subs_pq, "SELECT COUNT(*) AS n FROM data")
            result["subdomains_found"] = rows[0]["n"] if rows else 0
            top_subs = self.query_parquet(subs_pq, "SELECT subdomain FROM data LIMIT 10")
            result["top_subdomains"] = [r.get("subdomain", "") for r in top_subs]

        # Open ports from rustscan
        ports_pq = job_dir / "ports.parquet"
        if ports_pq.exists():
            rows = self.query_parquet(ports_pq, "SELECT COUNT(*) AS n FROM data")
            result["open_ports_found"] = rows[0]["n"] if rows else 0
            top_ports = self.query_parquet(
                ports_pq,
                "SELECT port FROM data ORDER BY CAST(port AS INTEGER) LIMIT 20"
            )
            result["open_ports"] = [r.get("port") for r in top_ports]

        # Vulnerabilities from nuclei
        vulns_pq = job_dir / "vulns.parquet"
        if vulns_pq.exists():
            sev_rows = self.query_parquet(
                vulns_pq,
                "SELECT severity, COUNT(*) AS n FROM data GROUP BY severity ORDER BY n DESC"
            )
            result["severity_counts"] = {r["severity"]: r["n"] for r in sev_rows}
            result["total_vulns"] = sum(r["n"] for r in sev_rows)

            top_vulns = self.query_parquet(
                vulns_pq,
                "SELECT severity, title, detail FROM data ORDER BY "
                "CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 "
                "WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END LIMIT 10"
            )
            result["top_vulns"] = top_vulns

        return result

    def global_stats(self) -> dict[str, Any]:
        """
        Aggregate stats across ALL job Parquets (used by /stats and text-to-sql).
        Returns counters for subdomains, ports, vulns discovered.
        """
        stats: dict[str, Any] = {}

        try:
            vuln_rows = self.query_glob(
                "data/*/vulns.parquet",
                "SELECT severity, COUNT(*) AS n FROM data GROUP BY severity"
            )
            stats["total_vulns_by_severity"] = {r["severity"]: r["n"] for r in vuln_rows}
            stats["total_vulns"] = sum(r["n"] for r in vuln_rows)
        except Exception as exc:
            log.debug("global_stats vulns: %s", exc)
            stats["total_vulns"] = 0

        try:
            sub_rows = self.query_glob(
                "data/*/subs.parquet",
                "SELECT COUNT(DISTINCT subdomain) AS n FROM data"
            )
            stats["total_subdomains"] = sub_rows[0]["n"] if sub_rows else 0
        except Exception:
            stats["total_subdomains"] = 0

        try:
            port_rows = self.query_glob(
                "data/*/ports.parquet",
                "SELECT COUNT(*) AS n FROM data"
            )
            stats["total_open_ports"] = port_rows[0]["n"] if port_rows else 0
        except Exception:
            stats["total_open_ports"] = 0

        return stats

    def list_parquets(self, job_id: str | None = None) -> list[dict[str, Any]]:
        """
        List all Parquet files under data/.
        If job_id given, scoped to that job's directory.
        """
        base = DATA_DIR / job_id if job_id else DATA_DIR
        files = list(base.rglob("*.parquet")) if base.exists() else []
        result = []
        for f in sorted(files):
            try:
                size = f.stat().st_size
                rel = str(f.relative_to(DATA_DIR))
            except Exception:
                size, rel = 0, str(f)
            result.append({"path": rel, "size_bytes": size})
        return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. PgStore — PostgreSQL write-through
# ─────────────────────────────────────────────────────────────────────────────

class PgStore:
    """
    Thin wrapper over the Postgres schema defined in install.py.

    All methods are synchronous and raise gracefully when Postgres is
    unavailable (so the daemon keeps running even without a DB).

    Schema (from install.py):
        targets   (id, value, type, created_at)
        scans     (id, target_id, tool, status, parquet_path, created_at, updated_at)
        vulns     (id, scan_id, severity, title, detail, created_at)
        alerts    (id, source, title, url, severity, sent, created_at)
        inference_log (id, provider, model, tokens_in, tokens_out, cost_usd, cache_hit)
    """

    def _conn(self):
        """Return a live psycopg2 connection, or raise on failure."""
        return _pg_connect()

    # ── Targets ───────────────────────────────────────────────────────────

    def upsert_target(self, value: str, type_: str = "domain") -> int:
        """
        Insert target if it doesn't exist, return its ID.
        Type: domain | ip | cidr | url
        """
        try:
            conn = self._conn()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO targets (value, type)
                    VALUES (%s, %s)
                    ON CONFLICT (value) DO UPDATE SET value = EXCLUDED.value
                    RETURNING id
                    """,
                    (value, type_),
                )
                tid = cur.fetchone()[0]
            conn.close()
            return tid
        except Exception as exc:
            log.debug("upsert_target failed: %s", exc)
            return -1

    def get_targets(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return most-recently created targets."""
        try:
            conn = self._conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, value, type, created_at FROM targets ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            log.debug("get_targets failed: %s", exc)
            return []

    # ── Scans ─────────────────────────────────────────────────────────────

    def record_scan(
        self,
        target_id: int,
        tool: str,
        status: str = "pending",
        parquet_path: str | None = None,
    ) -> int:
        """Insert a new scan row, return scan ID."""
        try:
            conn = self._conn()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scans (target_id, tool, status, parquet_path)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (target_id, tool, status, parquet_path),
                )
                sid = cur.fetchone()[0]
            conn.close()
            return sid
        except Exception as exc:
            log.debug("record_scan failed: %s", exc)
            return -1

    def update_scan_status(
        self,
        scan_id: int,
        status: str,
        parquet_path: str | None = None,
    ) -> None:
        """Update scan status (and optionally parquet path)."""
        try:
            conn = self._conn()
            conn.autocommit = True
            with conn.cursor() as cur:
                if parquet_path:
                    cur.execute(
                        """
                        UPDATE scans
                        SET status = %s, parquet_path = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (status, parquet_path, scan_id),
                    )
                else:
                    cur.execute(
                        "UPDATE scans SET status = %s, updated_at = NOW() WHERE id = %s",
                        (status, scan_id),
                    )
            conn.close()
        except Exception as exc:
            log.debug("update_scan_status failed: %s", exc)

    def get_scans(
        self,
        target_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return scan rows, optionally filtered by target_id or status."""
        try:
            conn = self._conn()
            clauses, params = [], []
            if target_id is not None:
                clauses.append("target_id = %s")
                params.append(target_id)
            if status:
                clauses.append("status = %s")
                params.append(status)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(limit)
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, target_id, tool, status, parquet_path, created_at "
                    f"FROM scans {where} ORDER BY created_at DESC LIMIT %s",
                    params,
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            log.debug("get_scans failed: %s", exc)
            return []

    # ── Vulns ─────────────────────────────────────────────────────────────

    def record_vulns(
        self,
        scan_id: int,
        findings: list[dict[str, Any]],
    ) -> int:
        """Bulk insert vulnerability findings. Returns count inserted."""
        if not findings or scan_id < 0:
            return 0
        try:
            conn = self._conn()
            conn.autocommit = True
            count = 0
            with conn.cursor() as cur:
                for f in findings:
                    cur.execute(
                        """
                        INSERT INTO vulns (scan_id, severity, title, detail)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            scan_id,
                            f.get("severity", "info"),
                            f.get("title", "")[:500],
                            json.dumps(f),
                        ),
                    )
                    count += 1
            conn.close()
            return count
        except Exception as exc:
            log.debug("record_vulns failed: %s", exc)
            return 0

    def get_vulns(
        self,
        scan_id: int | None = None,
        severity: str | None = None,
        days: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch vulnerability records.

        Args:
            scan_id:  Filter by scan (None = all)
            severity: Filter by severity string
            days:     Only return findings from the last N days
            limit:    Max rows returned
        """
        try:
            conn = self._conn()
            clauses: list[str] = []
            params: list[Any] = []

            if scan_id is not None:
                clauses.append("scan_id = %s")
                params.append(scan_id)
            if severity:
                clauses.append("severity = %s")
                params.append(severity.lower())
            if days:
                clauses.append("created_at >= NOW() - INTERVAL '%s days'")
                params.append(days)

            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(limit)

            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, scan_id, severity, title, created_at "
                    f"FROM vulns {where} ORDER BY created_at DESC LIMIT %s",
                    params,
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            log.debug("get_vulns failed: %s", exc)
            return []

    # ── Alerts ────────────────────────────────────────────────────────────

    def record_alert(
        self,
        source: str,
        title: str,
        url: str | None = None,
        severity: str | None = None,
    ) -> int:
        """Insert a CVE/RSS alert. Returns alert ID or -1 on failure."""
        try:
            conn = self._conn()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alerts (source, title, url, severity)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (source, title[:500], url, severity),
                )
                aid = cur.fetchone()[0]
            conn.close()
            return aid
        except Exception as exc:
            log.debug("record_alert failed: %s", exc)
            return -1

    def mark_alert_sent(self, alert_id: int) -> None:
        try:
            conn = self._conn()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("UPDATE alerts SET sent = TRUE WHERE id = %s", (alert_id,))
            conn.close()
        except Exception as exc:
            log.debug("mark_alert_sent failed: %s", exc)

    def get_unsent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            conn = self._conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, source, title, url, severity, created_at "
                    "FROM alerts WHERE sent = FALSE ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            log.debug("get_unsent_alerts failed: %s", exc)
            return []

    # ── Aggregate stats (0 inference — used by /stats) ────────────────────

    def get_stats(self) -> dict[str, Any]:
        """
        Return a stats snapshot used by /stats Telegram command.
        Pure SQL — zero inference tokens.
        """
        stats: dict[str, Any] = {}
        try:
            conn = self._conn()
            with conn.cursor() as cur:
                # Target / scan counts
                cur.execute("SELECT COUNT(*) FROM targets")
                stats["targets_total"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM scans WHERE status = 'done'")
                stats["scans_done"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM scans WHERE status = 'running'")
                stats["scans_running"] = cur.fetchone()[0]

                # Vuln severity breakdown
                cur.execute(
                    "SELECT severity, COUNT(*) FROM vulns GROUP BY severity ORDER BY 2 DESC"
                )
                stats["vulns_by_severity"] = dict(cur.fetchall())
                stats["vulns_total"] = sum(stats["vulns_by_severity"].values())

                # Unsent alerts
                cur.execute("SELECT COUNT(*) FROM alerts WHERE sent = FALSE")
                stats["unsent_alerts"] = cur.fetchone()[0]

                # Inference cost (last 30 days) from postgres inference_log
                cur.execute(
                    """
                    SELECT COALESCE(SUM(cost_usd), 0), COALESCE(SUM(tokens_in + tokens_out), 0)
                    FROM inference_log
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                    """
                )
                cost, tokens = cur.fetchone()
                stats["inference_cost_30d"] = round(float(cost), 6)
                stats["inference_tokens_30d"] = int(tokens)

            conn.close()
        except Exception as exc:
            log.debug("get_stats Postgres failed: %s", exc)
            stats["error"] = str(exc)

        return stats


# ─────────────────────────────────────────────────────────────────────────────
# 3. TextToSQL — natural language → SQL bridge
# ─────────────────────────────────────────────────────────────────────────────

# Schema context injected into the LLM system prompt so it knows the tables.
_SCHEMA_CONTEXT = """
You have access to the following DuckDB views (over Parquet files):
  subdomains(subdomain TEXT)                         -- from amass
  ports(port TEXT)                                   -- from rustscan
  vulns(severity TEXT, title TEXT, detail TEXT)      -- from nuclei

And the following PostgreSQL tables:
  targets(id, value TEXT, type TEXT, created_at)
  scans(id, target_id, tool TEXT, status TEXT, created_at)
  vulns(id, scan_id, severity TEXT, title TEXT, created_at)
  alerts(id, source TEXT, title TEXT, url TEXT, severity TEXT, sent BOOL, created_at)
  inference_log(id, provider TEXT, model TEXT, tokens_in INT, tokens_out INT, cost_usd NUMERIC)

Respond with ONE valid SQL query only. No prose, no Markdown fences.
If the question cannot be answered with SQL, reply: UNSUPPORTED
""".strip()

# Canonical pre-built SQL for frequently asked questions (0 inference — cache seeded at startup)
_PREBUILT_SQL: dict[str, str] = {
    "how many critical vulns": (
        "SELECT COUNT(*) AS critical_vulns FROM vulns WHERE severity = 'critical'"
    ),
    "how many high vulns": (
        "SELECT COUNT(*) AS high_vulns FROM vulns WHERE severity = 'high'"
    ),
    "top 10 vulns": (
        "SELECT severity, title, COUNT(*) AS n FROM vulns "
        "GROUP BY severity, title ORDER BY n DESC LIMIT 10"
    ),
    "vuln summary": (
        "SELECT severity, COUNT(*) AS n FROM vulns GROUP BY severity ORDER BY n DESC"
    ),
    "how many targets": (
        "SELECT COUNT(*) AS total_targets FROM targets"
    ),
    "unsent alerts": (
        "SELECT source, title, severity, created_at FROM alerts WHERE sent = FALSE ORDER BY created_at DESC LIMIT 20"
    ),
    "inference cost": (
        "SELECT provider, model, SUM(cost_usd) AS cost, SUM(tokens_in+tokens_out) AS tokens "
        "FROM inference_log GROUP BY provider, model ORDER BY cost DESC"
    ),
    "recent scans": (
        "SELECT t.value AS target, s.tool, s.status, s.created_at "
        "FROM scans s JOIN targets t ON t.id = s.target_id "
        "ORDER BY s.created_at DESC LIMIT 20"
    ),
}


def _normalise_question(q: str) -> str:
    """Lower-case, strip punctuation for fuzzy matching against prebuilt SQL."""
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()


class TextToSQL:
    """
    Convert natural-language questions to SQL and execute them.

    PRD rule: SQL cache hits for analytics → 0 inference
    Strategy:
      1. Exact match against prebuilt SQL dict  (0 tokens)
      2. Cache check (exact + semantic)          (0 tokens on hit)
      3. LLM generation (inference.py tier=low)  (tokens only on miss)
      4. Execute SQL against DuckDB or Postgres
      5. Store result in cache for future hits
    """

    def __init__(self, duck: DuckStore, pg: PgStore | None = None) -> None:
        self._duck = duck
        self._pg   = pg

    async def answer(
        self,
        question: str,
        execute: bool = True,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Translate *question* to SQL and optionally execute it.

        Returns:
            {
                "question": str,
                "sql": str,
                "source": "prebuilt" | "cache" | "llm",
                "rows": list[dict] | None,   # None when execute=False
                "error": str | None,
            }
        """
        sql, source = self._resolve_sql(question)

        if sql == "UNSUPPORTED":
            return {
                "question": question,
                "sql": "UNSUPPORTED",
                "source": source,
                "rows": None,
                "error": "Question cannot be answered with available SQL tables",
            }

        if not execute:
            return {"question": question, "sql": sql, "source": source, "rows": None, "error": None}

        rows, error = self._execute_sql(sql, job_id=job_id)

        # Cache the result keyed on the question (for future identical questions)
        if not error and rows is not None:
            import cache as cache_module
            cache_module.store(f"t2s:{question}", json.dumps(rows[:50]))

        return {
            "question": question,
            "sql": sql,
            "source": source,
            "rows": rows,
            "error": error,
        }

    def _resolve_sql(self, question: str) -> tuple[str, str]:
        """
        Priority:
          1. Prebuilt exact keyword match (0 tokens)
          2. Cache exact/semantic match   (0 tokens)
          3. LLM                          (tokens spent, async — run_in_executor)
        Returns (sql_string, source_label).
        """
        norm = _normalise_question(question)

        # ── 1. Prebuilt match ─────────────────────────────────────────────
        for keyword, sql in _PREBUILT_SQL.items():
            if keyword in norm:
                log.debug("TextToSQL: prebuilt match for '%s'", keyword)
                return sql, "prebuilt"

        # ── 2. Cache check (synchronous via cache module) ─────────────────
        try:
            import cache as cache_module
            cached = cache_module.check(f"t2s:sql:{question}")
            if cached:
                log.debug("TextToSQL: cache hit for question")
                return cached, "cache"
        except Exception:
            pass

        # ── 3. LLM (synchronous wrapper — this blocks) ────────────────────
        try:
            import inference  # local module
            sql = inference.ask_sync(
                prompt=f"Question: {question}",
                tier="low",
                system=_SCHEMA_CONTEXT,
                temperature=0.1,
                max_tokens=256,
            )
            sql = sql.strip().lstrip("```sql").lstrip("```").rstrip("```").strip()

            # Cache the generated SQL keyed on the question
            try:
                import cache as cache_module
                cache_module.store(f"t2s:sql:{question}", sql)
            except Exception:
                pass

            return sql, "llm"
        except Exception as exc:
            log.warning("TextToSQL LLM generation failed: %s", exc)
            return "UNSUPPORTED", "error"

    def _execute_sql(
        self,
        sql: str,
        job_id: str | None = None,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """
        Execute SQL against DuckDB (Parquet) or Postgres depending on tables used.

        Heuristic: if SQL references DuckDB-only views (subdomains/ports), run
        in DuckDB. Otherwise fall through to Postgres.
        """
        sql_lower = sql.lower()
        uses_parquet = any(
            t in sql_lower for t in ("subdomains", "vulns_parquet", "ports_parquet", "parquet")
        )

        # DuckDB execution (Parquet-backed)
        if uses_parquet and job_id:
            try:
                import duckdb  # type: ignore
                job_dir = DATA_DIR / job_id
                con = duckdb.connect()
                self._register_duckdb_views(con, job_dir)
                result = con.execute(sql)
                cols = [d[0] for d in result.description]
                rows = [dict(zip(cols, r)) for r in result.fetchall()]
                con.close()
                return rows, None
            except Exception as exc:
                return None, f"DuckDB error: {exc}"

        # Postgres execution (schema tables)
        if self._pg:
            try:
                conn = self._pg._conn()
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                conn.close()
                return rows, None
            except Exception as exc:
                return None, f"Postgres error: {exc}"

        # Fallback: DuckDB without Parquet (runs SQL over empty views)
        try:
            import duckdb  # type: ignore
            con = duckdb.connect()
            if job_id:
                self._register_duckdb_views(con, DATA_DIR / job_id)
            result = con.execute(sql)
            cols = [d[0] for d in result.description]
            rows = [dict(zip(cols, r)) for r in result.fetchall()]
            con.close()
            return rows, None
        except Exception as exc:
            return None, f"Execution error: {exc}"

    @staticmethod
    def _register_duckdb_views(con: Any, job_dir: Path) -> None:
        """Register Parquet files as DuckDB views for a job."""
        view_map = {
            "subdomains":    job_dir / "subs.parquet",
            "ports":         job_dir / "ports.parquet",
            "vulns_parquet": job_dir / "vulns.parquet",
        }
        for view_name, pq_path in view_map.items():
            if pq_path.exists():
                con.execute(f"CREATE VIEW {view_name} AS SELECT * FROM '{pq_path}'")


# ─────────────────────────────────────────────────────────────────────────────
# 4. suggest_next_from_data — rule-based, 0 inference
# ─────────────────────────────────────────────────────────────────────────────

def suggest_next_from_data(
    duck: DuckStore,
    job_id: str,
    pg: PgStore | None = None,
) -> list[dict[str, Any]]:
    """
    Derive suggested next scanning steps purely from data — zero inference.

    Rules (evaluated in priority order):
      - critical/high vulns found      → deep_nuclei, manual review
      - web ports (80/443/8080) found  → gobuster, ffuf, nikto
      - ssh (22) found                 → ssh_audit, hydra
      - subdomains found               → vhost_scan, httpx sweep
      - any vulns at all               → vuln_prioritise (inference.prioritise_vulns)
      - no findings                    → port_scan expansion, passive osint

    Returns list of step dicts: {"action": str, "reason": str, "priority": int}
    """
    agg = duck.aggregate(job_id)
    suggestions: list[dict[str, Any]] = []

    sev_counts: dict[str, int] = agg.get("severity_counts", {})
    open_ports: list     = [str(p) for p in agg.get("open_ports", [])]
    total_vulns: int     = agg.get("total_vulns", 0)
    total_subs: int      = agg.get("subdomains_found", 0)

    crit_high = sev_counts.get("critical", 0) + sev_counts.get("high", 0)

    # P1 — critical or high severity findings
    if crit_high > 0:
        suggestions.append({
            "action":   "nuclei --severity critical,high",
            "reason":   f"{crit_high} critical/high finding(s) — confirm and deepen",
            "priority": 1,
        })
        suggestions.append({
            "action":   "manual_review",
            "reason":   "Critical findings require human verification",
            "priority": 1,
        })

    # P2 — web ports detected
    web_ports = {"80", "443", "8080", "8443", "8000", "3000"}
    found_web = set(open_ports) & web_ports
    if found_web:
        suggestions.append({
            "action":   f"gobuster dir -u http://TARGET:{','.join(sorted(found_web))}",
            "reason":   f"HTTP port(s) open: {', '.join(sorted(found_web))}",
            "priority": 2,
        })
        suggestions.append({
            "action":   "ffuf -u http://TARGET/FUZZ -w /usr/share/wordlists/dirb/common.txt",
            "reason":   "Directory fuzzing complements gobuster",
            "priority": 3,
        })
        suggestions.append({
            "action":   "nikto -h TARGET",
            "reason":   "Web server fingerprint and misconfiguration scan",
            "priority": 3,
        })

    # P3 — SSH
    if "22" in open_ports:
        suggestions.append({
            "action":   "ssh_audit TARGET",
            "reason":   "SSH port open — check algorithms, banners, CVEs",
            "priority": 2,
        })

    # P4 — SMB/NetBIOS
    smb_ports = {"445", "139"}
    if set(open_ports) & smb_ports:
        suggestions.append({
            "action":   "netexec smb TARGET --shares",
            "reason":   "SMB/NetBIOS open — enumerate shares",
            "priority": 2,
        })

    # P5 — Database ports exposed
    db_ports = {"3306": "mysql", "5432": "postgres", "27017": "mongodb",
                "6379": "redis", "9200": "elasticsearch"}
    for port, db in db_ports.items():
        if port in open_ports:
            suggestions.append({
                "action":   f"nmap -sV -p {port} --script={db} TARGET",
                "reason":   f"{db} port {port} exposed — check auth and version",
                "priority": 2,
            })

    # P6 — Subdomains discovered → sweep them
    if total_subs > 0:
        suggestions.append({
            "action":   f"httpx -l subs.parquet -status-code -title -tech-detect",
            "reason":   f"{total_subs} subdomain(s) found — fingerprint live ones",
            "priority": 3,
        })

    # P7 — Vulns found but none critical → medium prioritisation
    if total_vulns > 0 and crit_high == 0:
        med_low = sev_counts.get("medium", 0) + sev_counts.get("low", 0)
        suggestions.append({
            "action":   "vuln_prioritise",
            "reason":   f"{med_low} medium/low finding(s) — run LLM priority ranking",
            "priority": 4,
        })

    # P8 — Nothing found → expand scope
    if not suggestions:
        suggestions.append({
            "action":   "amass enum -passive -d TARGET",
            "reason":   "No findings yet — expand passive recon",
            "priority": 5,
        })
        suggestions.append({
            "action":   "masscan -p1-65535 TARGET --rate 1000",
            "reason":   "Full port sweep — rustscan may have missed ports",
            "priority": 5,
        })

    # Sort by priority, deduplicate actions
    seen: set[str] = set()
    final: list[dict[str, Any]] = []
    for s in sorted(suggestions, key=lambda x: x["priority"]):
        if s["action"] not in seen:
            seen.add(s["action"])
            final.append(s)

    log.debug("suggest_next_from_data: %d suggestions for job %s", len(final), job_id)
    return final


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singletons
# ─────────────────────────────────────────────────────────────────────────────

_duck: DuckStore | None = None
_pg: PgStore | None = None
_t2s: TextToSQL | None = None


def get_duck() -> DuckStore:
    global _duck
    if _duck is None:
        _duck = DuckStore()
    return _duck


def get_pg() -> PgStore:
    global _pg
    if _pg is None:
        _pg = PgStore()
    return _pg


def get_t2s() -> TextToSQL:
    global _t2s
    if _t2s is None:
        _t2s = TextToSQL(get_duck(), get_pg())
    return _t2s


# ─────────────────────────────────────────────────────────────────────────────
# CLI self-test / admin tool
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="HexClaw data.py — admin / self-test")
    sub = parser.add_subparsers(dest="cmd")

    # duck stats
    p_duck = sub.add_parser("duck-stats", help="Print global DuckDB stats")

    # pg stats
    p_pg = sub.add_parser("pg-stats", help="Print Postgres stats")

    # list parquets
    p_ls = sub.add_parser("ls", help="List Parquet files")
    p_ls.add_argument("--job", default=None)

    # aggregate job
    p_agg = sub.add_parser("aggregate", help="Aggregate a job's Parquet outputs")
    p_agg.add_argument("job_id")

    # suggest next
    p_sug = sub.add_parser("suggest", help="Rule-based next-step suggestions for a job")
    p_sug.add_argument("job_id")

    # text-to-sql
    p_t2s = sub.add_parser("ask", help="Natural-language query (text-to-sql)")
    p_t2s.add_argument("question", nargs="+")

    # write test data
    p_seed = sub.add_parser("seed", help="Write test Parquet data for a job_id")
    p_seed.add_argument("job_id")

    args = parser.parse_args()
    duck = get_duck()
    pg   = get_pg()
    t2s  = get_t2s()

    if args.cmd == "duck-stats":
        stats = duck.global_stats()
        print(json.dumps(stats, indent=2, default=str))

    elif args.cmd == "pg-stats":
        stats = pg.get_stats()
        print(json.dumps(stats, indent=2, default=str))

    elif args.cmd == "ls":
        files = duck.list_parquets(args.job)
        for f in files:
            print(f"{f['size_bytes']:>10} bytes  {f['path']}")
        print(f"\n{len(files)} Parquet file(s)")

    elif args.cmd == "aggregate":
        agg = duck.aggregate(args.job_id)
        print(json.dumps(agg, indent=2, default=str))

    elif args.cmd == "suggest":
        steps = suggest_next_from_data(duck, args.job_id, pg)
        for i, s in enumerate(steps, 1):
            print(f"\n[P{s['priority']}] Step {i}: {s['action']}")
            print(f"       Reason: {s['reason']}")

    elif args.cmd == "ask":
        question = " ".join(args.question)
        result = asyncio.run(t2s.answer(question))
        print(f"Question : {result['question']}")
        print(f"SQL      : {result['sql']}")
        print(f"Source   : {result['source']}")
        if result["error"]:
            print(f"Error    : {result['error']}")
        elif result["rows"] is not None:
            print(f"Rows     : {len(result['rows'])}")
            for row in result["rows"][:10]:
                print(f"  {row}")

    elif args.cmd == "seed":
        job_id = args.job_id
        n_subs = duck.store_records(
            DATA_DIR / job_id / "subs.parquet",
            [{"subdomain": f"sub{i}.example.com"} for i in range(5)],
        )
        n_ports = duck.store_records(
            DATA_DIR / job_id / "ports.parquet",
            [{"port": str(p)} for p in [22, 80, 443, 8080, 3306]],
        )
        n_vulns = duck.store_records(
            DATA_DIR / job_id / "vulns.parquet",
            [
                {"severity": "critical", "title": "Log4Shell RCE",   "detail": "CVE-2021-44228"},
                {"severity": "high",     "title": "SQL Injection",    "detail": "login form"},
                {"severity": "medium",   "title": "Missing HSTS",     "detail": "header not set"},
                {"severity": "low",      "title": "Server Version",   "detail": "nginx/1.18.0"},
                {"severity": "info",     "title": "Open Port",        "detail": "22/tcp"},
            ],
        )
        print(f"Seeded job {job_id}: {n_subs} subs, {n_ports} ports, {n_vulns} vulns")
        print(f"  Run: python data.py aggregate {job_id}")
        print(f"  Run: python data.py suggest {job_id}")

    else:
        parser.print_help()
