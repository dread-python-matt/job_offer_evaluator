def company_from_model(model: str) -> str:
    if model.startswith("gemini"):
        return "Google"
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "OpenAI"
    if model.startswith("claude"):
        return "Anthropic"
    return "Unknown"
