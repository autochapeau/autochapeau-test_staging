import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from nacl.exceptions import CryptoError

from website_bundle import decrypt, encrypt


class TestPrivateWebsiteBundle(unittest.TestCase):
    def setUp(self):
        key = Ed25519PrivateKey.generate()
        self.public = key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                                     serialization.PublicFormat.OpenSSH)
        self.private = key.private_bytes(serialization.Encoding.PEM,
                                        serialization.PrivateFormat.OpenSSH,
                                        serialization.NoEncryption())

    def test_round_trip_and_randomized_ciphertext(self):
        payload = b"private frontend build" * 10000
        sealed = encrypt(payload, self.public)
        self.assertNotIn(b"private frontend build", sealed)
        self.assertEqual(decrypt(sealed, self.private), payload)
        self.assertNotEqual(sealed, encrypt(payload, self.public))

    def test_tampering_is_rejected(self):
        sealed = bytearray(encrypt(b"private build", self.public))
        sealed[-1] ^= 1
        with self.assertRaises(CryptoError):
            decrypt(bytes(sealed), self.private)

    def test_other_deployment_key_cannot_decrypt(self):
        other = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH, serialization.NoEncryption())
        with self.assertRaises(CryptoError):
            decrypt(encrypt(b"private build", self.public), other)


if __name__ == "__main__":
    unittest.main()
