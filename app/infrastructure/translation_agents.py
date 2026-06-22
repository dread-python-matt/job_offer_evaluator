from agents import Agent

_POLISH_TO_ENGLISH_INSTRUCTIONS = (
    "You are a professional translator specializing in IT job offer content. "
    "Translate the provided job offer text from Polish to English. "
    "Preserve all technical terms, formatting, and the professional tone of the original. "
    "Translate only what is given — do not add, remove, or interpret any content."
)

_ENGLISH_TO_POLISH_INSTRUCTIONS = (
    "You are a professional translator specializing in IT job offer content. "
    "Translate the provided job offer text from English to Polish. "
    "Preserve all technical terms, formatting, and the professional tone of the original. "
    "Translate only what is given — do not add, remove, or interpret any content."
)


def build_polish_to_english_agent(model: str | None = None) -> Agent:
    return Agent(
        name="Polish-to-English Job Offer Translator",
        instructions=_POLISH_TO_ENGLISH_INSTRUCTIONS,
        model=model,
    )


def build_english_to_polish_agent(model: str | None = None) -> Agent:
    return Agent(
        name="English-to-Polish Job Offer Translator",
        instructions=_ENGLISH_TO_POLISH_INSTRUCTIONS,
        model=model,
    )
