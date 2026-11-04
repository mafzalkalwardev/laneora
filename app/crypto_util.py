"""CryptoJS-compatible OpenSSL Salted__ AES-CBC helpers (from recovered appv2.3)."""
from __future__ import annotations

import binascii
import hashlib
from typing import Any

from Crypto.Cipher import AES


def evp_kdf(
    passwd: str | bytes,
    salt: bytes,
    key_size: int = 8,
    iv_size: int = 4,
    iterations: int = 1,
    hash_algorithm: str = "md5",
) -> dict[str, Any]:
    """OpenSSL EVP_BytesToKey-style derivation used by CryptoJS."""
    if isinstance(passwd, str):
        passwd = passwd.encode("utf-8")
    target_key_size = key_size + iv_size
    derived_bytes = b""
    block = b""
    hasher_name = hash_algorithm.lower()
    number_of_derived_words = 0
    while number_of_derived_words < target_key_size:
        hasher = hashlib.new(hasher_name)
        hasher.update(block + passwd + salt)
        block = hasher.digest()
        for _ in range(1, iterations):
            hasher = hashlib.new(hasher_name)
            hasher.update(block)
            block = hasher.digest()
        derived_bytes += block
        number_of_derived_words = len(derived_bytes) // 4
    key = derived_bytes[: key_size * 4]
    return {"key": key, "iv": derived_bytes[key_size * 4 : target_key_size * 4]}


def _pkcs7_unpad(text: str) -> str:
    if not text:
        return text
    pad = ord(text[-1])
    if pad < 1 or pad > 16:
        return text
    return text[:-pad]


def decrypt(passphrase: str, encrypted_text: str) -> str:
    """Decrypt CryptoJS AES OpenSSL-compatible ciphertext (Salted__ + base64)."""
    encrypted_text_bytes = binascii.a2b_base64(encrypted_text)
    # strip "Salted__" prefix
    encrypted_text_bytes = encrypted_text_bytes[8:]
    salt = encrypted_text_bytes[:8]
    encrypted_text_bytes = encrypted_text_bytes[8:]
    # key_size=12 words → 48 bytes → AES-256 key (32) + IV (16)
    resp = evp_kdf(passphrase, salt, key_size=12)
    key = resp["key"]
    iv = key[len(key) - 16 :]
    key = key[: len(key) - 16]
    aes = AES.new(key, AES.MODE_CBC, iv)
    decrypted_text = aes.decrypt(encrypted_text_bytes)
    return _pkcs7_unpad(decrypted_text.decode("utf-8"))
