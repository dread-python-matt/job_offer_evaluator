_COMPANY_REGISTRY: list[tuple[str | tuple[str, ...], str]] = [
    ("gemini", "Google"),
    (("gpt-", "o1-", "o3-", "o4-"), "OpenAI"),
    ("claude", "Anthropic"),
]


def company_from_model(model: str) -> str:
    for prefix, company in _COMPANY_REGISTRY:
        if model.startswith(prefix):
            return company
    return "Unknown"
