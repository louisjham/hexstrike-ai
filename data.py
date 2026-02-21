"""
HexClaw — data.py
================
Hybrid analytical data engine.

PRD compliance:
  • DuckDB (':memory:') for fast analytical queries on local findings.
  • psycopg2 for persistence/heavy lookups in Postgres.
  • query(prompt): text-to-sql -> DataFrame.
  • store_parquet(df, name): save results for persistence.
  • suggest_next(workflow_id): Internal logic to pick next actions based on data.
"""

import logging
import os
import sqlite3
from typing import Any, List, Optional

import duckdb
import pandas as pd
from dotenv import load_dotenv

import inference

load_dotenv()

log = logging.getLogger("hexclaw.data")

# ── Config ────────────────────────────────────────────────────────────────────
from config import DATA_DIR, JOBS_DB

# ── Engines ───────────────────────────────────────────────────────────────────
_duck = duckdb.connect(':memory:')

def get_duck():
    return _duck

def get_pg_conn():
    """Return a psycopg2 connection if POSTGRES_DSN is set."""
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        return None
    try:
        import psycopg2
        return psycopg2.connect(dsn)
    except Exception as e:
        log.warning(f"Postgres connection failed: {e}")
        return None

# ── Analytics ─────────────────────────────────────────────────────────────────
async def query(prompt: str) -> pd.DataFrame:
    """
    Translate natural language to SQL and run against DuckDB.
    In v1.0, this is a 'Thrifty' shim using LLM only for SQL generation.
    """
    # 1. Get Schema (simplified for v1.0)
    schema = "Tables: jobs(id, skill, target, status), token_log(provider, model, cost)" 
    
    # 2. Text-to-SQL or Direct SQL
    if any(keyword in prompt.upper() for keyword in ["SELECT ", "WITH ", "DESCRIBE "]):
        sql = prompt
    else:
        sql_prompt = f"Convert this request to a DuckDB SQL query. Only respond with the SQL.\nSchema: {schema}\nRequest: {prompt}"
        sql = await inference.ask(sql_prompt, complexity="med", system="You are a SQL expert. Output ONLY valid DuckDB SQL.")
    
    # Clean SQL if LLM included backticks or returned an error message
    sql = sql.replace("```sql", "").replace("```", "").strip()
    if sql.startswith("Error:"):
        log.error(f"LLM returned error instead of SQL: {sql}")
        return pd.DataFrame()
    
    log.info(f"Executing SQL: {sql}")
    
    # 3. Execute
    try:
        # JOBS_DB imported from config at module level
        _duck.execute("INSTALL sqlite; LOAD sqlite;")
        _duck.execute(f"ATTACH IF NOT EXISTS '{JOBS_DB}' AS main_jobs (TYPE SQLITE)")
        
        # Set search path so 'jobs' works without 'main_jobs.' prefix
        _duck.execute("SET search_path = 'main_jobs,main'")
        
        df = _duck.query(sql).to_df()
        return df
    except Exception as e:
        log.error(f"Data query failed: {e}")
        return pd.DataFrame()

def store_parquet(df: pd.DataFrame, name: str):
    """Store results as Parquet in the data directory."""
    path = DATA_DIR / f"{name}.parquet"
    df.to_parquet(path)
    log.info(f"Stored {len(df)} rows to {path}")

# ── Workflows ─────────────────────────────────────────────────────────────────
def suggest_next(workflow_id: str) -> List[str]:
    """
    Rule-based + SQL suggestion logic.
    Analyzes findings for a job and suggests logical next steps.
    """
    # Placeholder: In a real run, this would query the 'findings' table for current workflow_id
    # If open ports found -> "Vuln Scan"
    # If HTTP found -> "Deep Probe"
    # If CVE found -> "Exploit CVE"
    
    # Simulating data-driven logic
    suggestions = ["Deep scan target", "Identify tech stack"]
    
    # Logic: if ports table exists and has entries for this workflow
    try:
        res = _duck.query(f"SELECT COUNT(*) FROM read_parquet('{DATA_DIR}/*.parquet') WHERE severity = 'high'").fetchone()
        if res and res[0] > 0:
            suggestions.insert(0, "Exploit CVE")
    except:
        pass
        
    return suggestions[:4]

# ── Telegram Integration ─────────────────────────────────────────────────────
async def get_summary_df() -> str:
    """Returns a markdown summary of the last 5 jobs for Telegram."""
    df = await query("Show me the last 5 jobs and their status")
    if df.empty:
        return "No job data available."
    return df.to_markdown(index=False)
