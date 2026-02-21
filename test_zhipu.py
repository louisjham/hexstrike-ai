import litellm
import os
from dotenv import load_dotenv

load_dotenv()

print(f"LiteLLM version: {litellm.__version__}")
# print(f"Providers: {litellm.provider_list}")

try:
    response = litellm.completion(
        model="glm-4",
        custom_llm_provider="zhipuai",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10
    )
    print("Success with custom_llm_provider='zhipuai'")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Failed with custom_llm_provider='zhipuai': {e}")

try:
    # Some versions use 'zhipuai' as a prefix but it might need to be 'zhipu/'
    response = litellm.completion(
        model="zhipu/glm-4",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10
    )
    print("Success with zhipu/glm-4")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Failed with zhipu/glm-4: {e}")
