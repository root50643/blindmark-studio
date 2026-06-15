from app.security import SecretCipher
from app.watermark import derive_seeds


def test_secret_cipher_round_trip():
    cipher = SecretCipher({"v1": b"k" * 32}, "v1")
    encrypted = cipher.encrypt("秘密口令")
    assert encrypted is not None
    assert cipher.decrypt(*encrypted) == "秘密口令"
    assert "秘密口令" not in encrypted


def test_seed_derivation_is_stable_and_separated():
    first = derive_seeds("hello")
    assert first == derive_seeds("hello")
    assert first[0] != first[1]
    assert first != derive_seeds("different")
