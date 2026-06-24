from app.infrastructure.argon2_password_hasher import Argon2PasswordHasher


def test_hash_is_not_the_plaintext():
    hasher = Argon2PasswordHasher()

    hashed = hasher.hash("correct horse battery")

    assert hashed != "correct horse battery"
    assert hashed.startswith("$argon2")


def test_verify_accepts_the_correct_password():
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("correct horse battery")

    assert hasher.verify("correct horse battery", hashed) is True


def test_verify_rejects_a_wrong_password():
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("correct horse battery")

    assert hasher.verify("wrong password", hashed) is False


def test_verify_returns_false_for_a_malformed_hash_instead_of_raising():
    hasher = Argon2PasswordHasher()

    assert hasher.verify("anything", "not-a-real-hash") is False


def test_two_hashes_of_the_same_password_differ_due_to_salt():
    hasher = Argon2PasswordHasher()

    assert hasher.hash("same password") != hasher.hash("same password")
