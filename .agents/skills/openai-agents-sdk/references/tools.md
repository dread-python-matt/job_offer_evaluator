# Tools

## Function tools

`@function_tool` wraps a Python function as an agent-callable tool, generating its JSON schema from the signature and docstring (Pydantic-validated args).

```python
from agents import function_tool

@function_tool
async def fetch_weather(location: str) -> str:
    """Fetch the weather for a given location.

    Args:
        location: The location to fetch the weather for.
    """
    return "sunny"
```

- Both sync and async functions are supported.
- Add a first parameter typed `RunContextWrapper[T]` (or `ToolContext[T]`) to access local context/dependencies inside the tool — see [running-and-context.md](running-and-context.md).
- `name_override` / `timeout` / `failure_error_function` customize behavior (see below).

## Hosted tools

Run server-side via `OpenAIResponsesModel`, no local infrastructure needed:

| Tool | Purpose |
|------|---------|
| `WebSearchTool` | Web search, with optional location filtering |
| `FileSearchTool` | Retrieval from OpenAI Vector Stores, with filtering |
| `CodeInterpreterTool` | Sandboxed code execution |
| `ImageGenerationTool` | Generate images from prompts |
| `ComputerTool` | GUI/browser automation — implement `Computer`/`AsyncComputer` |
| `ShellTool` | Shell execution, locally or in a hosted container |
| `HostedMCPTool` | Exposes a remote MCP server's tools |

## Timeouts

```python
@function_tool(timeout=2.0)
async def slow_lookup(query: str) -> str:
    return f"Result for {query}"
```

- `"error_as_result"` (default): on timeout, the model sees a timeout message and can recover/retry.
- `"raise_exception"`: raises `ToolTimeoutError`, failing the run.

## Error handling

```python
def my_error_handler(context, error):
    return "An error occurred. Please try again."

@function_tool(failure_error_function=my_error_handler)
def get_profile(user_id: str) -> str:
    """Fetch user profile."""
    return profile_data
```

Pass `failure_error_function=None` to re-raise errors yourself instead of surfacing a message to the model.
