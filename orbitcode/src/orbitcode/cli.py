"""Command line: orbitcode encode | decode | keygen | serve"""
import argparse
import sys

from . import __version__, core, secure


def build_parser():
    ap = argparse.ArgumentParser(prog="orbitcode", description="OrbitCode: MonoOrbit / ColourOrbit + optional SecureOrbit")
    ap.add_argument("-V", "--version", action="version", version=f"orbitcode {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("encode", help="make a code image")
    e.add_argument("text", nargs="?")
    e.add_argument("-f", "--file", help="read the data from a file instead")
    e.add_argument("-o", "--out", default="orbit.png")
    e.add_argument("--scale", type=float, default=2.0, help="image size factor (1 = 1000 px)")
    e.add_argument("--version", choices=core.VERSIONS, default="mono", help="mono (print) or colour (screen)")
    e.add_argument("--password", help="SecureOrbit: encrypt with this password")
    e.add_argument("--sign-key", help="SecureOrbit: Ed25519 private key (hex) to sign with")
    d = sub.add_parser("decode", help="read one or more images of the same code")
    d.add_argument("images", nargs="+")
    d.add_argument("-o", "--out", help="write the data to a file instead of the terminal")
    d.add_argument("--password")
    d.add_argument("--verify-key", help="SecureOrbit: Ed25519 public key (hex) to verify the signature")
    sub.add_parser("keygen", help="make a signing key pair")
    s = sub.add_parser("serve", help="start the web interface (needs: pip install orbitcode[web])")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=5000)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "keygen":
        priv, pub = secure.new_keypair()
        print(f"private (secret!): {priv}\npublic:            {pub}")
    elif a.cmd == "encode":
        data = open(a.file, "rb").read() if a.file else (a.text or "").encode()
        try:
            core.encode(data, a.version, a.scale, a.password, a.sign_key).save(a.out)
        except ValueError as ex:
            return f"error: {ex}"
        cap = core.capacity(a.version, bool(a.password), bool(a.sign_key))
        print(f"saved {a.out} ({a.version}, {len(data)} bytes, capacity ~{cap} bytes)")
    elif a.cmd == "decode":
        import cv2
        imgs = [cv2.imread(p) for p in a.images]
        if any(i is None for i in imgs):
            return "error: could not read one of the images"
        try:
            data, info = core.decode_images(imgs, a.password, a.verify_key)
        except ValueError as ex:
            return f"error: {ex}"
        sys.stderr.write(f"{info}\n")
        if a.out:
            open(a.out, "wb").write(data)
        else:
            sys.stdout.buffer.write(data + b"\n")
    else:
        try:
            from .web import run
        except ImportError:
            return "error: the web interface needs Flask: pip install 'orbitcode[web]'"
        run(a.host, a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
