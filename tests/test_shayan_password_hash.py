"""shayan has only a pbkdf2 hash. Other restored accounts still have plaintext."""
from __future__ import annotations

import base64
import hashlib
import secrets
import unittest

from server import soft_shim


def _hash(password: str, rounds: int = 600_000) -> str:
    folded = soft_shim._client_secret(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", folded.encode("utf-8"), salt, rounds)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${rounds}${salt_b64}${digest_b64}"


class FindUserHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self._accounts = soft_shim._all_accounts
        self.users = [
            {"username": "dispatcher2", "password": "PlainSecret"},
            {"username": "shayan", "password_hash": _hash("ShayanSecret1")},
        ]
        soft_shim._all_accounts = lambda: self.users

    def tearDown(self) -> None:
        soft_shim._all_accounts = self._accounts

    def test_plaintext_account_still_matches_v3_lowercase(self) -> None:
        found = soft_shim._find_user("Dispatcher2", "plainsecret")
        self.assertIsNotNone(found)
        self.assertEqual(found["username"], "dispatcher2")
        self.assertIsNone(soft_shim._find_user("dispatcher2", "wrong-secret"))

    def test_hash_only_account_matches_lowercased_password(self) -> None:
        found = soft_shim._find_user("shayan", "ShayanSecret1")
        self.assertIsNotNone(found)
        self.assertEqual(found["username"], "shayan")
        self.assertTrue(found["password_hash"].startswith("pbkdf2_sha256$600000$"))

    def test_hash_only_account_rejects_wrong_password(self) -> None:
        self.assertIsNone(soft_shim._find_user("shayan", "not-the-password"))

    def test_invalid_hash_fails_closed(self) -> None:
        self.users[1] = {"username": "shayan", "password_hash": "pbkdf2_sha256$nope"}
        self.assertIsNone(soft_shim._find_user("shayan", "pbkdf2_sha256$nope"))
        self.users[1] = {"username": "shayan", "password_hash": "pbkdf2_sha256$600000$%%%$%%%"}
        self.assertIsNone(soft_shim._find_user("shayan", "ShayanSecret1"))

    def test_missing_secret_fails_closed(self) -> None:
        self.users[1] = {"username": "shayan"}
        self.assertIsNone(soft_shim._find_user("shayan", "ShayanSecret1"))


if __name__ == "__main__":
    unittest.main()
