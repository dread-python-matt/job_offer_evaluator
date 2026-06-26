def estimate_tokens(text: str) -> int:
    """A rough token count (~4 characters per token) for when the provider doesn't report
    usage. Deliberately simple and dependency-free; callers flag the result as `estimated`
    so it is never mistaken for a measured count."""
    return (len(text) + 3) // 4
