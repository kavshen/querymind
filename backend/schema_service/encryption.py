"""
encryption.py

WHY THIS FILE EXISTS:
A connection string like "postgresql://user:mypassword@host/db" contains a
plaintext DB password. If QueryMind ever stores these, we must NOT store the
raw string. Fernet gives us reversible (symmetric) encryption: we encrypt to
store safely, and decrypt only when we actually need to open a DB connection.
"""

from cryptography.fernet import Fernet
import os


def get_encryption_key() -> bytes:
    """Loads the encryption key from the environment variable QUERYMIND_SECRET_KEY."""
    key = os.environ.get("QUERYMIND_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "QUERYMIND_SECRET_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and put it in your .env file."
        )
    return key.encode()


def encrypt_string(plain_text: str) -> str:
    """Encrypts a plain string (like a connection string) into a safe-to-store token."""
    f = Fernet(get_encryption_key())
    encrypted_bytes = f.encrypt(plain_text.encode())
    return encrypted_bytes.decode()


def decrypt_string(encrypted_text: str) -> str:
    """Reverses encrypt_string -- turns the stored token back into the real value."""
    f = Fernet(get_encryption_key())
    decrypted_bytes = f.decrypt(encrypted_text.encode())
    return decrypted_bytes.decode()
