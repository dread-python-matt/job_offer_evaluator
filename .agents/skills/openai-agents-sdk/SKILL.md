---
name: openai-agents-sdk
description: Reference for building agents with OpenAI's Agents SDK (the Python `agents` package: `Agent`, `Runner`, `function_tool`, `handoff`, guardrails, sessions, tracing). Use when the user mentions the OpenAI Agents SDK, writes `from agents import ...`, builds multi-agent handoff/orchestration flows on OpenAI models, or wants to add tool-use, guardrails, memory, or tracing on top of the OpenAI API. Not for Anthropic's Claude Agent SDK, LangChain, or CrewAI.
---

# OpenAI Agents SDK

Python framework for building single- and multi-agent LLM apps on the OpenAI API. Three core primitives: **Agents** (LLM + instructions + tools), **Handoffs** (agent-to-agent delegation), **Guardrails** (input/output validation).

Install: `pip install openai-agents`

## Quick start

```python
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="You are a helpful assistant")
result = Runner.run_sync(agent, "Write a haiku about recursion.")
print(result.final_output)
```

`Runner` drives the loop: call the model → if it returns final text, stop; if it calls a tool, run it and feed the result back; if it triggers a handoff, switch the active agent; repeat until done. Use `Runner.run()` (async) or `Runner.run_streamed()` for streaming events instead of `run_sync()`.

## Agent class

Key constructor args: `name` (required), `instructions` (string, or a sync/async `(context, agent) -> str` function for dynamic prompts), `model`, `model_settings` (temperature, `tool_choice`), `tools`, `output_type` (Pydantic/dataclass for structured output instead of free text), `handoffs`, `input_guardrails`/`output_guardrails`, `mcp_servers`.

`tool_choice` on `model_settings`: `"auto"` (default), `"required"`, `"none"`, or a specific tool name. The SDK resets it to `"auto"` after each call to avoid infinite tool-use loops.

Clone an agent instead of redefining it: `pirate_agent.clone(name="Robot", instructions="Write like a robot")`.

## Reference files

| File | Read when... |
|------|---------------|
| [references/tools.md](references/tools.md) | Defining function tools or using hosted tools (web search, file search, code interpreter, computer use) |
| [references/handoffs-and-guardrails.md](references/handoffs-and-guardrails.md) | Delegating between agents, or validating input/output |
| [references/running-and-context.md](references/running-and-context.md) | Runner methods, `RunConfig`, exceptions, or passing local dependencies via context |
| [references/sessions-and-tracing.md](references/sessions-and-tracing.md) | Adding cross-turn memory, or debugging/observing a run |
| [references/orchestration-patterns.md](references/orchestration-patterns.md) | Designing a multi-agent system (which orchestration style to pick) |

## Common pitfalls

- The local `context` object passed to `Runner.run(..., context=...)` is **never** sent to the model — it's for tools/callbacks only. To put something in front of the LLM, put it in instructions, input, or a tool result. See [references/running-and-context.md](references/running-and-context.md).
- Without a `Session`, no memory persists between separate `Runner.run()` calls — each call is stateless unless you pass history back in yourself. See [references/sessions-and-tracing.md](references/sessions-and-tracing.md).
- A handoff is exposed to the model as a tool (`transfer_to_<agent_name>`); if an agent isn't responding as expected after delegation, check `tool_name_override`/`input_filter` rather than assuming the model ignored the handoff. See [references/handoffs-and-guardrails.md](references/handoffs-and-guardrails.md).
- Output guardrails always run *after* the agent finishes — they can't cancel an in-flight model call the way input guardrails can. See [references/handoffs-and-guardrails.md](references/handoffs-and-guardrails.md).

## Sources

- [OpenAI Agents SDK (Python) — official docs](https://openai.github.io/openai-agents-python/)
- [Tools](https://openai.github.io/openai-agents-python/tools/)
- [Handoffs](https://openai.github.io/openai-agents-python/handoffs/)
- [Guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [Running agents](https://openai.github.io/openai-agents-python/running_agents/)
- [Sessions](https://openai.github.io/openai-agents-python/sessions/)
- [Agents](https://openai.github.io/openai-agents-python/agents/)
- [Tracing](https://openai.github.io/openai-agents-python/tracing/)
- [Context management](https://openai.github.io/openai-agents-python/context/)
- [Orchestrating multiple agents](https://openai.github.io/openai-agents-python/multi_agent/)
- [The next evolution of the Agents SDK | OpenAI](https://openai.com/index/the-next-evolution-of-the-agents-sdk/) (2026 update: sandboxing, long-horizon tasks, expanded observability)
