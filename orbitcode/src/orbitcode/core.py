"""One entry point for MonoOrbit, ColourOrbit and the optional SecureOrbit layer."""
import cv2
import numpy as np

from . import colour, mono, secure
from .secure import SecurityError

VERSIONS = {"mono": mono, "colour": colour}


def capacity(version="mono", password=False, sign=False):
    """Approximate max bytes (incompressible data) for the chosen options."""
    return VERSIONS[version].capacity() - secure.overhead(password, sign)


def encode(data, version="mono", scale=2.0, password=None, sign_key=None):
    """Returns a PIL image. password / sign_key switch SecureOrbit on; leave None for an open code."""
    if version not in VERSIONS:
        raise ValueError("version must be 'mono' or 'colour'")
    return VERSIONS[version].encode(secure.wrap(data, password or None, sign_key or None), scale)


def decode_images(imgs, password=None, verify_key=None):
    """imgs: list of BGR arrays (several frames of one code are combined).
    Returns (data, info). The version (mono/colour) is detected automatically."""
    light = np.median(cv2.cvtColor(imgs[0], cv2.COLOR_BGR2GRAY)) > 128      # white paper -> MonoOrbit
    order = ["mono", "colour"] if light else ["colour", "mono"]
    err = None
    for name in order:
        try:
            raw, used = VERSIONS[name].decode_images(imgs)
        except Exception as e:
            err = err or e
            continue
        data, info = secure.unwrap(raw, password or None, verify_key or None)   # SecurityError passes through
        return data, {"version": name, "frames": used, **info}
    raise err
