"""
HexClaw — awesome_skills.py
===========================
Bridge to the sickn33/antigravity-awesome-skills repository.
Allows HexClaw to dynamically load and utilize 800+ expert agentic skills.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from config import ROOT

log = logging.getLogger("hexclaw.awesome_skills")

SKILLS_DIR = ROOT / ".agent" / "skills"
INDEX_FILE = SKILLS_DIR / "skills_index.json"

_skills_indexCache: list[dict] = []

def get_skills_by_category() -> dict[str, list[dict]]:
    """
    Returns a dictionary grouping all loaded skills by their category.
    Returns: { "category_name": [{"name": "skill-name", "description": "..."}, ...] }
    """
    _load_index()
    categories = {}
    for skill in _skills_indexCache:
        cat = skill.get("category", "uncategorized")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "name": skill.get("name", ""),
            "description": skill.get("description", "")
        })
    return categories

def _load_index():
    """Lazily load the index JSON."""
    global _skills_indexCache
    if not _skills_indexCache and INDEX_FILE.exists():
        try:
            log.info(f"Loading awesome skills index from {INDEX_FILE}")
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                _skills_indexCache = json.load(f)
            log.info(f"Loaded {len(_skills_indexCache)} awesome skills.")
        except Exception as e:
            log.error(f"Failed to load awesome skills index: {e}")

def get_skill_by_name(skill_name: str) -> Optional[Dict[str, Any]]:
    """Fetch an exact skill by its ID/name, ignoring case."""
    _load_index()
    skill_name = skill_name.lower().strip()
    
    for skill in _skills_indexCache:
        if skill.get("id", "").lower() == skill_name or skill.get("name", "").lower() == skill_name:
            log.info(f"Loaded explicitly requested Awesome Skill: {skill.get('name')}")
            # Load the actual SKILL.md content
            skill_path = SKILLS_DIR / skill.get("path", "") / "SKILL.md"
            if skill_path.exists():
                try:
                    with open(skill_path, "r", encoding="utf-8") as f:
                        skill["raw_content"] = f.read()
                        return skill
                except Exception as e:
                    log.error(f"Failed to read skill content for {skill.get('name')}: {e}")
            else:
                log.warning(f"SKILL.md not found at {skill_path}")
    return None

def find_relevant_skill(goal: str, score_threshold: int = 2) -> Optional[Dict[str, Any]]:
    """
    Finds the most relevant skill for a given goal using basic keyword matching.
    Returns a dictionary containing the skill metadata and 'raw_content' if a match is found.
    """
    _load_index()
    if not _skills_indexCache:
        return None

    goal_lower = goal.lower()
    keywords = set(goal_lower.replace("-", " ").replace("_", " ").split())
    # Remove common stop words for better matching
    stop_words = {"a", "an", "the", "how", "to", "do", "i", "can", "you", "for", "with", "on", "in", "and", "or", "test", "write", "build"}
    keywords = keywords - stop_words

    best_match = None
    highest_score = 0

    for skill in _skills_indexCache:
        score = 0
        name_lower = skill.get("name", "").lower()
        desc_lower = skill.get("description", "").lower()

        for kw in keywords:
            if kw in name_lower:
                score += 3  # Name matches are weighted higher
            if kw in desc_lower:
                score += 1

        if score > highest_score:
            highest_score = score
            best_match = skill

    if best_match and highest_score >= score_threshold:
        log.info(f"Found awesome skill match: {best_match.get('name')} (Score {highest_score})")
        
        # Load the actual SKILL.md content
        skill_path = SKILLS_DIR / best_match.get("path", "") / "SKILL.md"
        if skill_path.exists():
            try:
                with open(skill_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    best_match["raw_content"] = content
                    return best_match
            except Exception as e:
                log.error(f"Failed to read skill content for {best_match.get('name')}: {e}")
        else:
            log.warning(f"SKILL.md not found at {skill_path}")
            
    return None
