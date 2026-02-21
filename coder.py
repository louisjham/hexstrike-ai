"""
HexClaw — coder.py
===================
Autonomous Code Generation & Execution Module.

This module leverages the core inference engine to write custom scripts 
to disk, execute them, and return the output.
"""

import asyncio
import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Tuple

from config import WORKSPACE_DIR
from inference import engine

log = logging.getLogger("hexclaw.coder")

SYSTEM_PROMPT = """You are the HexClaw autonomous coding module.
Your job is to generate a fully functioning, self-contained Python script to achieve the requested goal.
The script will be executed in a local environment.

CRITICAL RULES:
1. Output ONLY valid Python code inside a ```python block.
2. The script must be completely self-contained. Do not write incomplete snippets.
3. Import all necessary standard libraries (os, sys, json, requests, socket, etc.). If you need third-party libraries, assume reasonable modern ones like 'requests' or 'beautifulsoup4' are available.
4. If you need to output results, print them to stdout so they can be captured.
5. Do not include conversational filler before or after the code block.

Goal to achieve:
"""

async def generate_and_save_code(prompt: str, filename: str = "generated_script.py") -> Path:
    """Generate code using the LLM and save it to the workspace directory."""
    log.info(f"Generating code for prompt: '{prompt[:50]}...'")
    response_text = await engine.ask(
        prompt=prompt,
        complexity="med", # using med tier representing Z.ai GLM-4
        system=SYSTEM_PROMPT
    )
    
    # Extract code from markdown block
    code = _extract_code(response_text)
    if not code:
        log.warning("No code block found in LLM response! Storing raw response as script instead.")
        code = response_text
        
    script_path = WORKSPACE_DIR / filename
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)
    
    log.info(f"Code saved to {script_path} ({len(code)} bytes)")
    return script_path

def _extract_code(text: str) -> str:
    """Extract code from generic markdown blocks."""
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""

async def execute_script(script_path: Path, timeout: int = 30) -> Tuple[bool, str]:
    """Execute a Python script and capture its output."""
    log.info(f"Executing script: {script_path}")
    
    try:
        # Using subprocess.run asynchronously via asyncio.to_thread
        def _run():
            return subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORKSPACE_DIR)
            )
            
        import sys
        
        proc = await asyncio.to_thread(_run)
        
        output = proc.stdout
        if proc.stderr:
            output += "\n--- STDERR ---\n" + proc.stderr
            
        success = proc.returncode == 0
        if success:
            log.info(f"Script executed successfully. Return code: {proc.returncode}")
        else:
            log.error(f"Script failed with return code: {proc.returncode}")
            
        return success, output.strip()
        
    except subprocess.TimeoutExpired:
        log.error(f"Execution timed out after {timeout} seconds")
        return False, f"Error: Script execution timed out after {timeout} seconds."
    except Exception as e:
        log.error(f"Execution failed: {e}")
        return False, f"Execution error: {e}"

async def code_and_run(prompt: str) -> str:
    """High-level function: Ask LLM for code, write to disk, run it, return result."""
    script_path = await generate_and_save_code(prompt)
    success, output = await execute_script(script_path)
    
    result = f"--- Script Execution {'Succeeded' if success else 'Failed'} ---\n"
    result += f"{output}\n"
    return result
