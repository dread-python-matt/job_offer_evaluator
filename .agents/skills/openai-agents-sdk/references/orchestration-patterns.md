# Multi-Agent Orchestration Patterns

Pick based on how much control you need vs. how much you want the model to drive.

## LLM-driven orchestration

**Agents-as-tools** (`manager_agent = Agent(tools=[specialist.as_tool()])`): the manager keeps control of the conversation and calls specialists for bounded subtasks; the manager still produces the final user-facing reply. Use when a specialist should help but shouldn't take over the conversation.

**Handoffs** (see [handoffs-and-guardrails.md](handoffs-and-guardrails.md)): full control transfers to the specialist, which then replies directly as the active agent. Use when you want the specialist's own focused prompt/instructions to drive the rest of the turn, without the manager narrating the result.

Tactics that matter most for LLM-driven orchestration: invest in prompt quality per agent, use specialized (not generalist) agents, monitor and evaluate continuously, and let agents self-critique where useful.

## Code-driven orchestration

Deterministic, your code decides the path — trades flexibility for predictability of cost/speed/behavior:

- Structured output (`output_type=SomeModel`) to classify a task, then route in plain Python.
- Sequential chaining: pipe one agent's output into the next agent's input.
- Evaluator/feedback loop: run an agent, have a second agent (or guardrail) judge the result, loop until it passes a quality threshold.
- Parallel fan-out: run independent agents concurrently with `asyncio.gather`.

## Choosing

| Need | Pattern |
|------|---------|
| Specialist helps but manager stays in charge of the reply | Agents-as-tools |
| Specialist should own the rest of the conversation | Handoffs |
| Routing must be predictable/auditable | Code-driven (structured-output classification) |
| Independent subtasks, want lower latency | Code-driven (parallel `asyncio.gather`) |
| Output quality needs an explicit check-and-retry step | Code-driven (evaluator/feedback loop) |
