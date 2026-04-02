"""Show current configuration."""

import json

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

print("=" * 50)
print("CURRENT CONFIGURATION")
print("=" * 50)
print(f"join_delay_min: {config.get('join_delay_min')} seconds")
print(f"join_delay_max: {config.get('join_delay_max')} seconds")
print(f"daily_join_limit: {config.get('daily_join_limit')}")
print(f"llm_provider: {config.get('llm_provider')}")
print(f"llm_model: {config.get('llm_model')}")
print("=" * 50)
