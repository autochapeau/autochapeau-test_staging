"""Transport a private frontend build using the existing TEST SSH deployment key.

Only ciphertext is committed to this repository. Decryption happens on the
deployment runner; neither private keys nor plaintext builds are logged.
"""
import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from nacl.public import SealedBox
from nacl.signing import SigningKey, VerifyKey


def encrypt(payload, ssh_public_key):
    key = serialization.load_ssh_public_key(ssh_public_key)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("An Ed25519 TEST deployment key is required")
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return SealedBox(VerifyKey(raw).to_curve25519_public_key()).encrypt(payload)


def decrypt(payload, ssh_private_key):
    key = serialization.load_ssh_private_key(ssh_private_key, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("An Ed25519 TEST deployment key is required")
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    return SealedBox(SigningKey(raw).to_curve25519_private_key()).decrypt(payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("encrypt", "decrypt"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--public-key")
    arguments = parser.parse_args()
    payload = Path(arguments.input).read_bytes()
    if arguments.operation == "encrypt":
        result = encrypt(payload, Path(arguments.public_key).read_bytes())
    else:
        result = decrypt(payload, os.environ["SSH_PRIVATE_KEY"].encode())
    Path(arguments.output).write_bytes(result)
