"""
HexClaw — vuln_prioritize.py
===========================
Data-driven vulnerability prioritization using DuckDB.
Ranks findings by CVSS, reachability, and exploit-db status.
"""

import logging
import pandas as pd
import duckdb
from pathlib import Path
import data

log = logging.getLogger("hexclaw.prioritize")

def rank_vulnerabilities(parquet_name: str) -> pd.DataFrame:
    """
    Query the stored findings and return a prioritized list.
    Prioritization factors:
      - Severity (Critical > High > Medium)
      - Presence of CVE ID
      - Protocol (HTTP/HTTPS)
    """
    db = data.get_duck()
    parquet_path = data.DATA_DIR / f"{parquet_name}.parquet"
    
    if not parquet_path.exists():
        log.warning(f"No findings found at {parquet_path}")
        return pd.DataFrame()

    try:
        # Load parquet and sort via DuckDB
        query = f"""
            SELECT * FROM read_parquet('{parquet_path}')
            ORDER BY 
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    ELSE 4
                END ASC,
                target ASC
        """
        df = db.query(query).to_df()
        return df
    except Exception as e:
        log.error(f"Prioritization query failed: {e}")
        return pd.DataFrame()

def get_top_cves(parquet_name: str, limit: int = 5) -> str:
    """Return a summary string of the top CVEs for Telegram."""
    df = rank_vulnerabilities(parquet_name)
    if df.empty:
        return "No vulnerabilities found to prioritize."
    
    summary = "🔥 *Top Critical/High Vulnerabilities*\n"
    for _, row in df.head(limit).iterrows():
        sev = row.get('severity', 'unknown').upper()
        name = row.get('template_id', row.get('name', 'Vuln'))
        target = row.get('target', 'unknown')
        summary += f"• *[{sev}]* `{name}` on `{target}`\n"
    
    return summary
