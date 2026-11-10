"""SecureOrbit: optional security layer for MonoOrbit and ColourOrbit.

Off by default (open code, full capacity). The user may switch on either or both:
  * password encryption  - scrypt key derivation + ChaCha20-Poly1305 (AEAD)
  * signature            - Ed25519, proves who made the code and that it was not altered

Wire format:  flags(1) | [salt(16) nonce(12)] | body | [signature(64)]
  flags: 1 = encrypted, 2 = signed, 4 = compressed
  body : zlib(data) if compressed, then AEAD(body) (+16 byte tag) if encrypted
All primitives come from the `cryptography` package; nothing is home-made.
"""
import os
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

ENC, SIG, ZIP = 1, 2, 4
OVERHEAD = {"base": 1, "pw": 44, "sig": 64}      # bytes: flags / salt+nonce+tag / signature


class SecurityError(ValueError):
    pass


def overhead(password=False, sign=False):
    return OVERHEAD["base"] + (OVERHEAD["pw"] if password else 0) + (OVERHEAD["sig"] if sign else 0)


def _key(password, salt):
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(password.encode("utf-8"))


def new_keypair():
    """Returns (private_key_hex, public_key_hex). Keep the private key secret."""
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub = k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv.hex(), pub.hex()


def wrap(data, password=None, sign_key=None):
    """data -> bytes to store in the code. With no password/sign_key it stays open."""
    body = zlib.compress(data, 9)
    flags = ZIP if len(body) < len(data) else 0
    if not flags:
        body = data
    salt = nonce = b""
    if password:
        flags |= ENC
        salt, nonce = os.urandom(16), os.urandom(12)
    if sign_key:
        flags |= SIG
        try:
            signer = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(sign_key.strip()))
        except ValueError:
            raise SecurityError("স্বাক্ষরের private key ঠিক নয় (৬৪ অক্ষরের hex হতে হবে)।")
    if password:
        body = ChaCha20Poly1305(_key(password, salt)).encrypt(nonce, body, bytes([flags]) + salt)
    msg = bytes([flags]) + salt + nonce + body
    return msg + signer.sign(msg) if sign_key else msg


def unwrap(raw, password=None, verify_key=None):
    """bytes from the code -> (data, info). Raises SecurityError on any security failure."""
    if not raw:
        raise SecurityError("কোডে কোনো তথ্য নেই।")
    flags = raw[0]
    info = {"encrypted": bool(flags & ENC), "signature": "none"}
    if flags & SIG:
        if len(raw) < 65:
            raise SecurityError("কোড নষ্ট।")
        raw, sig = raw[:-64], raw[-64:]
        info["signature"] = "unchecked"
        if verify_key:
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(verify_key.strip())).verify(sig, raw)
            except Exception:
                raise SecurityError("স্বাক্ষর মেলেনি: কোডটি জাল, বদলানো, বা key ভুল।")
            info["signature"] = "valid"
    elif verify_key:
        raise SecurityError("এই কোডে স্বাক্ষর নেই, তাই যাচাই করা গেল না।")
    body = raw[1:]
    if flags & ENC:
        if not password:
            raise SecurityError("এই কোড পাসওয়ার্ড-সুরক্ষিত। পাসওয়ার্ড দিন।")
        salt, nonce, body = body[:16], body[16:28], body[28:]
        try:
            body = ChaCha20Poly1305(_key(password, salt)).decrypt(nonce, body, raw[:17])
        except InvalidTag:
            raise SecurityError("ভুল পাসওয়ার্ড, অথবা কোডটি বদলানো হয়েছে।")
    return (zlib.decompress(body) if flags & ZIP else body), info
