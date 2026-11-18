import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from insert_builder.database.provision import CarmaTenant


def _encrypt(plaintext: str, key: bytes):
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(iv).decode(), base64.b64encode(ciphertext).decode()


def test_password_decrypts_correctly(monkeypatch):
    key = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("PUBLISHER_ENCRYPTION_KEY", base64.b64encode(key).decode())

    iv_b64, ciphertext_b64 = _encrypt("s3cr3t-sql-password", key)
    tenant = CarmaTenant()
    tenant.encrypted_password = ciphertext_b64
    tenant.encrypted_password_iv = iv_b64

    assert tenant.password == "s3cr3t-sql-password"


def test_password_empty_when_key_missing(monkeypatch):
    monkeypatch.delenv("PUBLISHER_ENCRYPTION_KEY", raising=False)
    tenant = CarmaTenant()
    tenant.encrypted_password = "anything"
    tenant.encrypted_password_iv = "anything"

    assert tenant.password == ""


def test_password_empty_when_wrong_key(monkeypatch):
    real_key = AESGCM.generate_key(bit_length=256)
    wrong_key = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("PUBLISHER_ENCRYPTION_KEY", base64.b64encode(wrong_key).decode())

    iv_b64, ciphertext_b64 = _encrypt("s3cr3t-sql-password", real_key)
    tenant = CarmaTenant()
    tenant.encrypted_password = ciphertext_b64
    tenant.encrypted_password_iv = iv_b64

    # Wrong key -> GCM authentication tag mismatch -> caught -> empty string,
    # not an exception bubbling up.
    assert tenant.password == ""


def test_password_empty_when_no_encrypted_data(monkeypatch):
    monkeypatch.setenv("PUBLISHER_ENCRYPTION_KEY", base64.b64encode(AESGCM.generate_key(bit_length=256)).decode())
    tenant = CarmaTenant()
    assert tenant.password == ""
