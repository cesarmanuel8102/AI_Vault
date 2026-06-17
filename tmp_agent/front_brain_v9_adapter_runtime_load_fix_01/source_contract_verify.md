# Source Contract Verify

- openai_compat_exists: `True`
- main_exists: `True`
- main_includes_openai_compat_router: `True`
- models_source_exists: `True`
- chat_completions_source_exists: `True`
- imports_handle_user_message: `True`
- passed: `True`

## Forbidden Occurrences
- LLMManager.query: `False`
- .llm.query: `False`
- faiss.write_index: `False`
- semantic_memory.append: `False`
- broker: `False`
- trading: `False`
