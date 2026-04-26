from optimizer_service import _to_prompt_fields

raw = {'role': {'name':'assistant'}, 'task': {'text':'Do X'}, 'context': ['a','b'], 'constraints': 123}
fallback = {'role': None, 'task': 'Default Task', 'context': None, 'constraints': None}

try:
    result = _to_prompt_fields(raw, fallback)
    print("Resulting dict:")
    print(result)
except Exception as e:
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
