import asyncio
import os
import sys

# Ensure parent is in sys.path if run directly
parent_dir = os.path.dirname(os.path.abspath(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import coder

async def main():
    print("Testing HexClaw Coder...")
    prompt = "Write a simple script that prints 'Hello HexClaw Coding!'"
    
    result = await coder.code_and_run(prompt)
    print("\n--- Final Result ---")
    print(result)
    
if __name__ == "__main__":
    asyncio.run(main())
