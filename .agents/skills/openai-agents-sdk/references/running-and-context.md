# Running Agents and Context

## Runner methods

- `Runner.run(agent, input, context=None)` — async, returns `RunResult`
- `Runner.run_sync(...)` — sync wrapper around `run()`
- `Runner.run_streamed(...)` — async, returns `RunResultStreaming`, streaming events as the LLM generates them

## Agent loop

1. Call the model with the current agent + input.
2. Final text (no tool calls) → loop ends, becomes `result.final_output`.
3. Tool call(s) → execute, append results, go to 1.
4. Handoff → switch active agent, go to 1.
5. If `max_turns` is exceeded → raises `MaxTurnsExceeded` (pass `max_turns=None` to disable the limit).

## RunConfig

Pass `run_config=RunConfig(...)` to `Runner.run` to set run-wide overrides without editing agent definitions: model overrides, guardrails applied across all agents, tracing options (`workflow_name`, `trace_id`, `tracing_disabled`), tool-execution limits/approval policy, and conversation-state strategy (server-managed vs client-managed history).

## Exceptions

| Exception | Raised when |
|-----------|--------------|
| `MaxTurnsExceeded` | Run exceeds `max_turns` |
| `ModelBehaviorError` | Malformed model output or unexpected tool failure |
| `ToolTimeoutError` | A function tool exceeds its configured `timeout` (with `"raise_exception"` mode) |
| `UserError` | SDK misuse / invalid configuration |
| `InputGuardrailTripwireTriggered` / `OutputGuardrailTripwireTriggered` | A guardrail's tripwire fired |

## Local context vs LLM context

**Local context** (`RunContextWrapper[T]`) is your own Python object — dependencies, app state — passed via `Runner.run(agent, input, context=my_obj)`. Tools, `on_handoff` callbacks, and lifecycle hooks receive it wrapped. **It is never sent to the model.** Every component in one run must agree on the same context type `T`.

```python
wrapper.context        # your app object — mutable state/dependencies
wrapper.usage           # token/request metrics for the run so far
wrapper.tool_input      # structured input when running nested agents
wrapper.approve_tool()  # programmatic tool-approval control
wrapper.reject_tool()
```

Inside a tool, the context arrives as `ToolContext[T]` (extends `RunContextWrapper` with `tool_name`, `tool_call_id`, `tool_arguments`).

**LLM context** is only what's actually in the conversation. To get information in front of the model, you must use one of:

1. Agent instructions (static or dynamic)
2. The input passed to `Runner.run`
3. A function tool's return value
4. A retrieval/web-search tool result

If a tool seems to "not know" something you set on the context object, that's expected — move it into the prompt or a tool result instead.
