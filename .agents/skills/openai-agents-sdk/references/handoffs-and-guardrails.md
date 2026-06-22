# Handoffs and Guardrails

## Handoffs

Let one agent delegate to another specialist. The SDK exposes a handoff to the model as a tool named `transfer_to_<agent_name>`.

```python
from agents import Agent, handoff

billing_agent = Agent(name="Billing agent")
refund_agent = Agent(name="Refund agent")

triage_agent = Agent(
    name="Triage agent",
    handoffs=[billing_agent, handoff(refund_agent)],
)
```

Pass agents directly, or wrap with `handoff()` to customize:

- `tool_name_override` / `tool_description_override` — change how the handoff tool is presented to the model
- `on_handoff` — callback fired when the handoff occurs
- `input_type` — a Pydantic model the model must fill in when invoking the handoff (e.g. an escalation reason), passed to `on_handoff`
- `input_filter` — rewrites the conversation history the receiving agent sees, e.g. `handoff_filters.remove_all_tools`
- `is_enabled` — bool or callable to conditionally show/hide the handoff at runtime

```python
from pydantic import BaseModel
from agents import Agent, handoff, RunContextWrapper

class EscalationData(BaseModel):
    reason: str

async def on_handoff(ctx: RunContextWrapper[None], input_data: EscalationData):
    print(f"Escalation called with reason: {input_data.reason}")

handoff_obj = handoff(agent=agent, on_handoff=on_handoff, input_type=EscalationData)
```

Register one handoff per destination agent. Add `RECOMMENDED_PROMPT_PREFIX` (from `agents.extensions.handoff_prompt`) to an agent's instructions so it knows how to use handoffs.

## Guardrails

Validate input before the model runs, or output after it finishes. Both follow the same shape: a function returns `GuardrailFunctionOutput(output_info, tripwire_triggered)`; if `tripwire_triggered` is true, the SDK raises (`InputGuardrailTripwireTriggered` / `OutputGuardrailTripwireTriggered`) and halts execution.

```python
from agents import input_guardrail, Agent, Runner, RunContextWrapper, GuardrailFunctionOutput

@input_guardrail
async def math_guardrail(ctx: RunContextWrapper[None], agent: Agent, input: str) -> GuardrailFunctionOutput:
    result = await Runner.run(guardrail_agent, input, context=ctx.context)
    return GuardrailFunctionOutput(
        output_info=result.final_output,
        tripwire_triggered=result.final_output.is_math_homework,
    )

agent = Agent(
    name="Customer support agent",
    instructions="Help customers with questions.",
    input_guardrails=[math_guardrail],
)
```

- **Input guardrails** default to running *in parallel* with the agent call — cheaper checks can cancel before the expensive model finishes, though some tokens may already be spent. Make blocking instead if you need the check to complete first.
- **Output guardrails** always run *after* the agent completes (no parallel option), since they need the final output to inspect.
- Attach via `input_guardrails=[...]` / `output_guardrails=[...]` on `Agent(...)`.
