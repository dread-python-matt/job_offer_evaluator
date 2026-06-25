from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.application.refresh_tokens import (
    InvalidRefreshTokenError,
    RefreshTokenRecord,
    RefreshTokenRepository,
    RefreshTokenService,
)


class _FakeRefreshTokenRepository(RefreshTokenRepository):
    """In-memory store keyed by record id, with hash/family/user lookups."""

    def __init__(self) -> None:
        self.records: dict[str, RefreshTokenRecord] = {}

    def add(self, record: RefreshTokenRecord) -> None:
        self.records[record.id] = record

    def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        return next((r for r in self.records.values() if r.token_hash == token_hash), None)

    def mark_consumed(self, token_id: str, consumed_at: datetime) -> None:
        self.records[token_id] = replace(self.records[token_id], consumed_at=consumed_at)

    def revoke_family(self, family_id: str) -> None:
        self.records = {i: r for i, r in self.records.items() if r.family_id != family_id}

    def revoke_user(self, user_id: str) -> None:
        self.records = {i: r for i, r in self.records.items() if r.user_id != user_id}


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _service(repo: _FakeRefreshTokenRepository, clock: _Clock | None = None) -> RefreshTokenService:
    tokens = iter(f"raw-{i}" for i in range(1, 1000))
    ids = iter(f"id-{i}" for i in range(1, 1000))
    return RefreshTokenService(
        repository=repo,
        ttl=timedelta(days=14),
        clock=clock or _Clock(datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)),
        token_factory=lambda: next(tokens),
        id_factory=lambda: next(ids),
    )


def test_rotate_consumes_the_token_and_issues_a_new_one_for_the_same_user():
    repo = _FakeRefreshTokenRepository()
    service = _service(repo)
    token = service.issue("user-1")

    user_id, new_token = service.rotate(token)

    assert user_id == "user-1"
    assert new_token != token


def test_the_rotated_successor_can_itself_be_rotated():
    repo = _FakeRefreshTokenRepository()
    service = _service(repo)
    _, second = service.rotate(service.issue("user-1"))

    user_id, third = service.rotate(second)

    assert user_id == "user-1"
    assert third not in (second,)


def test_reusing_a_consumed_token_is_rejected_and_revokes_the_whole_family():
    repo = _FakeRefreshTokenRepository()
    service = _service(repo)
    token = service.issue("user-1")
    _, successor = service.rotate(token)  # `token` is now consumed

    # Replaying the consumed token is treated as theft.
    with pytest.raises(InvalidRefreshTokenError):
        service.rotate(token)

    # ...and it burns the family, so the legitimate successor is invalidated too.
    with pytest.raises(InvalidRefreshTokenError):
        service.rotate(successor)


def test_rotation_keeps_the_token_in_the_same_family():
    repo = _FakeRefreshTokenRepository()
    service = _service(repo)
    service.rotate(service.issue("user-1"))

    families = {record.family_id for record in repo.records.values()}
    assert len(families) == 1


def test_an_unknown_token_is_rejected():
    service = _service(_FakeRefreshTokenRepository())

    with pytest.raises(InvalidRefreshTokenError):
        service.rotate("never-issued")


def test_an_expired_token_is_rejected():
    repo = _FakeRefreshTokenRepository()
    clock = _Clock(datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc))
    service = _service(repo, clock=clock)
    token = service.issue("user-1")

    clock.now = clock.now + timedelta(days=14, seconds=1)

    with pytest.raises(InvalidRefreshTokenError):
        service.rotate(token)


def test_the_raw_token_is_never_stored_only_its_hash():
    repo = _FakeRefreshTokenRepository()
    service = _service(repo)

    token = service.issue("user-1")

    stored = next(iter(repo.records.values()))
    assert stored.token_hash != token
    assert token not in {stored.token_hash, stored.id, stored.family_id}


def test_revoke_invalidates_the_token_family():
    repo = _FakeRefreshTokenRepository()
    service = _service(repo)
    token = service.issue("user-1")

    service.revoke(token)

    with pytest.raises(InvalidRefreshTokenError):
        service.rotate(token)


def test_revoke_user_invalidates_all_of_that_users_tokens():
    repo = _FakeRefreshTokenRepository()
    service = _service(repo)
    first = service.issue("user-1")
    second = service.issue("user-1")
    other = service.issue("user-2")

    service.revoke_user("user-1")

    with pytest.raises(InvalidRefreshTokenError):
        service.rotate(first)
    with pytest.raises(InvalidRefreshTokenError):
        service.rotate(second)
    # A different user's token is untouched.
    assert service.rotate(other)[0] == "user-2"
