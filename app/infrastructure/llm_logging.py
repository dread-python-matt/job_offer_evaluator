import logging

from agents import enable_verbose_stdout_logging

# Loggers that carry the raw LLM traffic. The OpenAI SDK logs request options
# (including the JSON body) and response/error bodies on "openai" at DEBUG;
# httpx/httpcore log the request line and status. Both OpenAI and Gemini (via the
# OpenAI-compatible client) flow through these, so this covers either provider.
_LLM_LOGGERS = ("openai", "httpx", "httpcore")


def configure_llm_logging(enabled: bool) -> None:
    """Surface the raw LLM HTTP traffic and Agents SDK run traces on stdout so
    failures (e.g. a 400 from the model) can be inspected request-by-request.

    No-op when disabled, so production stays quiet. Toggle with LLM_DEBUG in .env."""
    if not enabled:
        return
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for name in _LLM_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG)
    enable_verbose_stdout_logging()
