"""Web interface. Needs Flask:  pip install 'orbitcode[web]'   then:  orbitcode-web"""
import argparse
import base64
import io

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

from . import core, secure


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

    @app.get("/")
    def index():
        caps = {"mono": core.capacity("mono"), "colour": core.capacity("colour"), "ovh": secure.OVERHEAD}
        return render_template("index.html", caps=caps)

    @app.post("/api/keygen")
    def keygen():
        priv, pub = secure.new_keypair()
        return jsonify(private=priv, public=pub)

    @app.post("/api/encode")
    def encode():
        j = request.get_json(silent=True) or {}
        text = j.get("text", "")
        if not text.strip():
            return jsonify(error="কিছু লেখা দিন।"), 400
        try:
            img = core.encode(text.encode("utf-8"), j.get("version", "mono"), 2.0,
                              j.get("password") or None, j.get("sign_key") or None)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return jsonify(image="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())

    @app.post("/api/decode")
    def decode():
        imgs = [cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
                for f in request.files.getlist("images")]
        imgs = [i for i in imgs if i is not None]
        if not imgs:
            return jsonify(error="ছবি পাওয়া যায়নি।"), 400
        try:
            data, info = core.decode_images(imgs, request.form.get("password") or None,
                                            request.form.get("verify_key") or None)
        except Exception as e:
            return jsonify(error=str(e)), 422
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = f"[বাইনারি ডেটা, {len(data)} বাইট] " + data[:64].hex()
        return jsonify(text=text, info=info)

    return app


def run(host="127.0.0.1", port=5000):
    if host not in ("127.0.0.1", "localhost"):
        print("warning: passwords and private keys are sent to this server; use only on a network you trust (prefer HTTPS).")
    create_app().run(host=host, port=port)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="orbitcode-web", description="OrbitCode web interface")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    a = ap.parse_args(argv)
    run(a.host, a.port)


if __name__ == "__main__":
    main()
