"""
HexClaw — planner.py
===================
Agent Planner for translating high-level goals into executable workflows.

v2.0: Uses LiteLLM for dynamic planning.
Fallback: Rule-based keyword matching.
"""

import logging
import os
from typing import Any

# Try to import litellm for dynamic planning
try:
    import litellm
except ImportError:
    litellm = None

log = logging.getLogger("hexclaw.planner")

def plan_goal(goal: str) -> dict[str, Any]:
    """
    Given a goal string, return a workflow definition.
    Workflow definition:
    {
        "skill": str,
        "params": dict,
        "steps": list (optional override)
    }
    """
    log.info("Planning for goal: %s", goal)
    
    # If API keys are available and litellm is installed, try LLM planning
    if litellm and os.getenv("GOOGLE_API_KEY"):
        return _plan_with_llm(goal)
    
    # Fallback: Rule-based planning
    return _plan_with_rules(goal)

def _plan_with_rules(goal: str) -> dict[str, Any]:
    goal_lower = goal.lower()
    
    # Domain extraction
    import re
    domain_match = re.search(r'([a-z0-9]+(-[a-z0-9]+)*\.)+([a-z]{2,})', goal_lower)
    target = domain_match.group(0) if domain_match else "unknown"
    
    # Cyber / Recon
    if any(kw in goal_lower for kw in ["scan", "recon", "domain", "vuln", "nuclei"]):
        return {
            "skill": "recon_osint",
            "params": {"target": target, "description": "Auto-planned recon based on goal"}
        }
    
    # Dev / Git
    if any(kw in goal_lower for kw in ["git", "clone", "deploy", "lint", "test"]):
        return {
            "skill": "dev_ops",
            "params": {"target": target, "action": "clone_and_test"}
        }
    
    # OSINT / Social
    if any(kw in goal_lower for kw in ["breach", "social", "darkweb", "email"]):
        return {
            "skill": "osint_mapping",
            "params": {"target": target}
        }
    
    # Default: agent_plan (generic)
    return {
        "skill": "agent_plan",
        "params": {"target": target, "goal": goal}
    }

def _plan_with_llm(goal: str) -> dict[str, Any]:
    """
    Experimental: LiteLLM planner.
    Uses a very low-token prompt to decide which skill to run.
    """
    try:
        model = os.getenv("PLANNER_MODEL", "gemini/gemini-1.5-flash")
        prompt = f"""
        You are the HexClaw Orchestrator. 
        Goal: "{goal}"
        Available Skills: [recon_osint, dev_ops, osint_mapping]
        
        Respond ONLY with a JSON object:
        {{"skill": "skill_name", "params": {{"target": "extracted_target"}}}}
        """
        
        # This is a placeholder for actual litellm call
        # response = litellm.completion(model=model, messages=[{"role": "user", "content": prompt}])
        # return json.loads(response.choices[0].message.content)
        
        # For now, fallback to rules until we verify LiteLLM environment
        return _plan_with_rules(goal)
    except Exception as e:
        log.error("LLM Planning failed: %s", e)
        return _plan_with_rules(goal)
