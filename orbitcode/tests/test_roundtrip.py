import base64
import io

import cv2
import pytest

import orbitcode as oc
from orbitcode import SecurityError, cli

MSG = "OrbitCode: আমার সোনার বাংলা".encode()


def read(img, tmp_path, name="c.png"):
    p = tmp_path / name
    img.save(p)
    return [cv2.imread(str(p))]


@pytest.mark.parametrize("version", ["mono", "colour"])
def test_open_roundtrip_and_autodetect(version, tmp_path):
    data, info = oc.decode_images(read(oc.encode(MSG, version), tmp_path))
    assert data == MSG
    assert info["version"] == version and not info["encrypted"] and info["signature"] == "none"


@pytest.mark.parametrize("version", ["mono", "colour"])
def test_password(version, tmp_path):
    imgs = read(oc.encode(MSG, version, password="pw1"), tmp_path)
    assert oc.decode_images(imgs, password="pw1")[0] == MSG
    with pytest.raises(SecurityError):
        oc.decode_images(imgs)
    with pytest.raises(SecurityError):
        oc.decode_images(imgs, password="wrong")


def test_signature(tmp_path):
    priv, pub = oc.new_keypair()
    imgs = read(oc.encode(MSG, "mono", password="pw", sign_key=priv), tmp_path)
    data, info = oc.decode_images(imgs, "pw", pub)
    assert data == MSG and info["signature"] == "valid" and info["encrypted"]
    with pytest.raises(SecurityError):
        oc.decode_images(imgs, "pw", oc.new_keypair()[1])
    assert oc.decode_images(imgs, "pw")[1]["signature"] == "unchecked"


def test_capacity_and_limits():
    assert oc.capacity("colour") > oc.capacity("mono") > oc.capacity("mono", True, True) > 0
    with pytest.raises(ValueError):
        oc.encode(b"x" * 5000 + bytes(range(256)) * 20)
    with pytest.raises(ValueError):
        oc.encode(b"x", version="nope")


def test_cli(tmp_path, capsys):
    out = str(tmp_path / "a.png")
    assert cli.main(["encode", "hello cli", "-o", out, "--password", "p"]) == 0
    assert cli.main(["decode", out]).startswith("error")          # password missing
    assert cli.main(["decode", out, "--password", "p"]) == 0
    assert b"hello cli" in capsys.readouterr().out.encode()
    assert cli.main(["keygen"]) == 0


def test_web(tmp_path):
    pytest.importorskip("flask")
    from orbitcode.web import create_app
    c = create_app().test_client()
    assert c.get("/").status_code == 200
    assert c.get("/static/style.css").status_code == 200
    j = c.post("/api/encode", json={"text": "ওয়েব", "version": "colour", "password": "x"}).get_json()
    png = base64.b64decode(j["image"].split(",")[1])
    r = c.post("/api/decode", data={"images": (io.BytesIO(png), "a.png"), "password": "x"},
               content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["text"] == "ওয়েব"
    r = c.post("/api/decode", data={"images": (io.BytesIO(png), "a.png")}, content_type="multipart/form-data")
    assert r.status_code == 422
