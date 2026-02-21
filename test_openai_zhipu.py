import litellm
import os
from dotenv import load_dotenv

load_dotenv()

try:
    response = litellm.completion(
        model="openai/glm-4.7",
        api_base="https://api.z.ai/api/coding/paas/v4",
        api_key=os.getenv("ZHIPUAI_API_KEY"),
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10
    )
    print("Success with OpenAI-compatible endpoint")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Failed with OpenAI-compatible endpoint: {e}")
