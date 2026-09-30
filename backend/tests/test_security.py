"""Tests for Argon2id password hashing and the rehash-on-login path."""

import pytest

from src.security import (
    MAX_PASSWORD_LENGTH,
    InvalidPassword,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_password_hash_round_trip():
    encoded = hash_password('test-password')
    assert verify_password('test-password', encoded)
    assert not verify_password('wrong-password', encoded)


def test_hash_is_argon2id_phc_string():
    encoded = hash_password('test-password')
    # PHC: $argon2id$v=19$m=65536,t=3,p=4$<salt>$<digest>
    parts = encoded.split('$')
    assert parts[0] == ''
    assert parts[1] == 'argon2id'
    assert parts[2].startswith('v=')
    assert parts[3] == 'm=65536,t=3,p=4'
    assert len(parts) == 6


def test_hash_is_not_the_raw_password():
    password = 'correct horse battery staple'
    encoded = hash_password(password)
    assert encoded != password
    assert password not in encoded


def test_hash_uses_a_fresh_salt_each_call():
    first = hash_password('same-password')
    second = hash_password('same-password')
    assert first != second
    # Both remain usable, which is the point of salting rather than breaking
    # round trips.
    assert verify_password('same-password', first)
    assert verify_password('same-password', second)


def test_verify_rejects_wrong_password():
    encoded = hash_password('right-password')
    assert verify_password('right-password', encoded) is True
    assert verify_password('Right-Password', encoded) is False
    assert verify_password('', encoded) is False
    assert verify_password('right-password ', encoded) is False


def test_verify_returns_false_on_malformed_stored_hash():
    for malformed in (
        '',
        'not-a-hash',
        '$argon2id$broken',
        '$argon2id$v=19$m=65536,t=3,p=4$onlysalt$',
        'sha256$abc$def',
        None,
        12345,
    ):
        assert verify_password('any-password', malformed) is False


def test_hash_rejects_empty_password():
    for empty in ('', ' ', '\t\n'):
        with pytest.raises(InvalidPassword):
            hash_password(empty)


def test_verify_of_empty_password_never_raises():
    encoded = hash_password('a-real-password')
    assert verify_password('', encoded) is False
    assert verify_password('   ', encoded) is False


def test_hash_rejects_very_long_password():
    too_long = 'x' * (MAX_PASSWORD_LENGTH + 1)
    with pytest.raises(InvalidPassword):
        hash_password(too_long)


def test_verify_of_very_long_password_never_raises():
    encoded = hash_password('a-real-password')
    too_long = 'x' * (MAX_PASSWORD_LENGTH + 10_000)
    assert verify_password(too_long, encoded) is False


def test_max_length_password_is_hashed():
    encoded = hash_password('y' * MAX_PASSWORD_LENGTH)
    assert verify_password('y' * MAX_PASSWORD_LENGTH, encoded)


def test_password_with_nul_character_is_rejected():
    with pytest.raises(InvalidPassword):
        hash_password('pass\x00word')


def test_unicode_and_whitespace_passwords_round_trip():
    for password in ('رمز عبور فارسی', 'pässwörd-🔐', ' leading and trailing '):
        encoded = hash_password(password)
        assert verify_password(password, encoded)


def test_needs_rehash_is_false_for_current_parameters():
    encoded = hash_password('test-password')
    assert needs_rehash('test-password', encoded) is False


def test_needs_rehash_is_true_for_weaker_stored_parameters():
    from argon2 import PasswordHasher

    weak = PasswordHasher(
        time_cost=1,
        memory_cost=8,
        parallelism=1,
        hash_len=16,
        salt_len=8,
    ).hash('test-password')
    assert needs_rehash('test-password', weak) is True
    # A rehash produces a hash the current parameters accept.
    upgraded = hash_password('test-password')
    assert needs_rehash('test-password', upgraded) is False
    assert verify_password('test-password', upgraded)


def test_needs_rehash_returns_false_for_malformed_hash():
    assert needs_rehash('test-password', 'not-a-hash') is False
    assert needs_rehash('test-password', '') is False
    assert needs_rehash('test-password', None) is False


def test_module_does_not_expose_a_sha256_password_path():
    import inspect

    from src import security

    source = inspect.getsource(security)
    assert 'sha256' not in source
    assert not hasattr(security, 'sha256')
