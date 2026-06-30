from types import SimpleNamespace

from app.infrastructure.openai_skill_embedder import OpenAISkillEmbedder


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def create(self, *, model, input):
        self.calls.append((model, list(input)))
        # One float per text (its length) — enough to assert wiring without a real model.
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[float(len(t))]) for t in input]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddings()


def test_embed_sends_texts_and_parses_vectors():
    client = _FakeClient()
    embedder = OpenAISkillEmbedder(client, model="m")

    vectors = embedder.embed(["ab", "cde"])

    assert vectors == [[2.0], [3.0]]
    assert client.embeddings.calls == [("m", ["ab", "cde"])]


def test_embed_empty_is_a_noop():
    client = _FakeClient()
    assert OpenAISkillEmbedder(client).embed([]) == []
    assert client.embeddings.calls == []
