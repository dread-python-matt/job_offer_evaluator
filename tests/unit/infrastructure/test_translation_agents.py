from app.infrastructure.translation_agents import (
    build_english_to_polish_agent,
    build_polish_to_english_agent,
)


def test_polish_to_english_agent_name_indicates_translation_direction():
    agent = build_polish_to_english_agent(model="test-model")

    assert "Polish" in agent.name
    assert "English" in agent.name


def test_english_to_polish_agent_name_indicates_translation_direction():
    agent = build_english_to_polish_agent(model="test-model")

    assert "English" in agent.name
    assert "Polish" in agent.name


def test_polish_to_english_agent_instructions_mention_job_offers():
    agent = build_polish_to_english_agent()

    assert "job" in agent.instructions.lower()


def test_english_to_polish_agent_instructions_mention_job_offers():
    agent = build_english_to_polish_agent()

    assert "job" in agent.instructions.lower()


def test_polish_to_english_agent_uses_the_provided_model():
    agent = build_polish_to_english_agent(model="gemini-2.5-flash")

    assert agent.model == "gemini-2.5-flash"


def test_english_to_polish_agent_uses_the_provided_model():
    agent = build_english_to_polish_agent(model="gemini-2.5-flash")

    assert agent.model == "gemini-2.5-flash"


def test_polish_to_english_and_english_to_polish_agents_are_distinct():
    pl_to_en = build_polish_to_english_agent()
    en_to_pl = build_english_to_polish_agent()

    assert pl_to_en.instructions != en_to_pl.instructions
    assert pl_to_en.name != en_to_pl.name
