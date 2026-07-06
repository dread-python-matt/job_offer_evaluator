from app.domain.auth import User
from app.domain.password_policy import validate_password_strength
from app.scripts.seed_user import (
    DEFAULT_DEMO_EMAIL,
    DEFAULT_DEMO_PASSWORD,
    seed_user,
)
from tests.fakes import FakePasswordHasher, FakeUserRepository


def test_seed_user_creates_a_verified_account():
    repo = FakeUserRepository()
    hasher = FakePasswordHasher()

    result = seed_user(repo, hasher, email=DEFAULT_DEMO_EMAIL, password=DEFAULT_DEMO_PASSWORD)

    assert result.created is True
    user = repo.get_by_email(DEFAULT_DEMO_EMAIL)
    assert user is not None
    # Verified so it can log in immediately (login is 403 until the email is confirmed).
    assert user.email_verified is True
    assert hasher.verify(DEFAULT_DEMO_PASSWORD, user.password_hash)


def test_seed_user_normalizes_the_email():
    repo = FakeUserRepository()
    hasher = FakePasswordHasher()

    seed_user(repo, hasher, email="  DEMO@Example.COM  ", password=DEFAULT_DEMO_PASSWORD)

    # Stored the same way registration would, so login (which normalizes too) matches.
    assert repo.get_by_email("demo@example.com") is not None


def test_seed_user_is_idempotent_and_does_not_duplicate():
    repo = FakeUserRepository()
    hasher = FakePasswordHasher()

    first = seed_user(repo, hasher, email=DEFAULT_DEMO_EMAIL, password=DEFAULT_DEMO_PASSWORD)
    second = seed_user(repo, hasher, email=DEFAULT_DEMO_EMAIL, password=DEFAULT_DEMO_PASSWORD)

    assert first.created is True
    assert second.created is False
    assert second.user_id == first.user_id  # same account, not a fresh one


def test_seed_user_does_not_overwrite_an_existing_password():
    existing = User(
        id="u-1",
        email=DEFAULT_DEMO_EMAIL,
        password_hash="hashed:original",
        email_verified=True,
    )
    repo = FakeUserRepository([existing])
    hasher = FakePasswordHasher()

    seed_user(repo, hasher, email=DEFAULT_DEMO_EMAIL, password="Different1!")

    # A pre-existing account is left untouched — its password is not clobbered.
    assert repo.get_by_email(DEFAULT_DEMO_EMAIL).password_hash == "hashed:original"


def test_seed_user_verifies_a_preexisting_unverified_account():
    existing = User(
        id="u-1",
        email=DEFAULT_DEMO_EMAIL,
        password_hash="hashed:whatever",
        email_verified=False,
    )
    repo = FakeUserRepository([existing])
    hasher = FakePasswordHasher()

    result = seed_user(repo, hasher, email=DEFAULT_DEMO_EMAIL, password=DEFAULT_DEMO_PASSWORD)

    assert result.created is False
    assert repo.get_by_email(DEFAULT_DEMO_EMAIL).email_verified is True


def test_default_demo_password_satisfies_the_password_policy():
    # The documented demo credentials must be a valid password, so the same account could be
    # created via the normal (policy-enforced) register/reset flows too.
    validate_password_strength(DEFAULT_DEMO_PASSWORD)  # must not raise
