"""OrbitCode: circular graph-based 2D codes.

MonoOrbit (black + grey, print-safe), ColourOrbit (8 colours, for screens)
and the optional SecureOrbit layer (password encryption, Ed25519 signature).

    import cv2, orbitcode as oc
    oc.encode(b"hello", version="mono", password="pw").save("a.png")
    data, info = oc.decode_images([cv2.imread("a.png")], password="pw")
"""
from .core import SecurityError, VERSIONS, capacity, decode_images, encode
from .secure import new_keypair

__version__ = "0.1.0"
__all__ = ["encode", "decode_images", "capacity", "new_keypair", "SecurityError", "VERSIONS", "__version__"]
