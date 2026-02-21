"""
HexClaw — config.py
===================
Single source of truth for shared paths and directory constants.

Every module that previously defined its own ROOT / DATA_DIR / LOG_DIR /
JOBS_DB / TOKEN_LOG_DB / SKILLS_DIR should import from here instead.
"""

from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
SKILLS_DIR = ROOT / "skills"
WORKSPACE_DIR = DATA_DIR / "workspace"

JOBS_DB = DATA_DIR / "jobs.db"
TOKEN_LOG_DB = DATA_DIR / "token_log.db"

# ── Ensure directories exist on first import ──────────────────────────────────
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
WORKSPACE_DIR.mkdir(exist_ok=True)
