# Sessions and Tracing

## Sessions (memory across runs)

Without a session, each `Runner.run()` call is stateless. A `Session` automatically prepends stored history before a run and appends new items (user input, assistant responses, tool calls) after it.

```python
from agents import SQLiteSession

session = SQLiteSession("user_123")                        # in-memory, lost on process exit
session = SQLiteSession("user_123", "conversations.db")    # persisted to a file

result = await Runner.run(agent, "hello", session=session)
```

Custom backend: implement `SessionABC` with `get_items()`, `add_items()`, `pop_item()` (removes the most recent item, for corrections), and `clear_session()`.

## Tracing (observability)

Every run auto-generates a **trace** (`workflow_name`, `trace_id`, optional `group_id`, `metadata`) made of **spans**: agent execution, LLM generation, function calls, guardrails, handoffs, audio ops. Defaults to exporting to the OpenAI dashboard via a `BatchTraceProcessor`.

```python
from agents import add_trace_processor, set_tracing_disabled

add_trace_processor(my_custom_processor)   # supplement the default export
# or: set_trace_processors([my_custom_processor])  # replace it entirely
```

For long-running services, call `flush_traces()` before shutdown so the final batch is delivered.

Disable tracing (any one of):
- env var `OPENAI_AGENTS_DISABLE_TRACING=1`
- `set_tracing_disabled(True)`
- `RunConfig(tracing_disabled=True)` per run

`RunConfig(trace_include_sensitive_data=False)` excludes LLM inputs/outputs, function parameters, and audio from exported spans while keeping the trace structure.
