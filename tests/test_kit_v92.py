"""Kit v92: images on cards (private-tasks card #292). `attach` writes an image under assets/<card id>/ beside the board
files and adds ![alt](assets/...) to a new comment or the description. The page side (paste, drop, the Image button and
showing images from the API) is tested in tests/browser/images.test.js; this file covers the CLI and pins the version."""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KIT = os.path.join(REPO, "board", "kit")
sys.path.insert(0, KIT)
import keeptrack  # noqa: E402
from board_fixtures import copy_board_fixture  # noqa: E402


def png(w=4, h=3):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


class Attach(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "board")
        copy_board_fixture("v4_kit72", self.dir)
        self.file = os.path.join(self.dir, "tasks.json")
        self.img = os.path.join(self.tmp.name, "Login page.png")
        with open(self.img, "wb") as f:
            f.write(png())

    def tearDown(self):
        self.tmp.cleanup()

    def run_kt(self, *args):
        env = {**os.environ, "BOARD_USER": "alexdemo", "BOARD_AGENT": "claude", "BOARD_SESSION": "a1b2c3d4"}
        return subprocess.run([sys.executable, os.path.join(KIT, "keeptrack.py"), "--file", self.file, *args],
                              capture_output=True, text=True, env=env, cwd=self.tmp.name)

    def card(self):
        old = keeptrack.FILE
        try:
            keeptrack.FILE = self.file; keeptrack._BOARD_STATES.clear()
            data, _ = keeptrack.load()
        finally:
            keeptrack.FILE = old; keeptrack._BOARD_STATES.clear()
        return next(t for t in data["tasks"] if t["id"] == "t_first")

    def assets(self):
        base = os.path.join(self.dir, "assets", "t_first")
        return sorted(os.listdir(base)) if os.path.isdir(base) else []

    def test_attach_writes_the_file_and_a_comment(self):
        r = self.run_kt("attach", "t_first", self.img, "The login page after the change")
        self.assertEqual(0, r.returncode, r.stderr)
        [name] = self.assets()
        self.assertRegex(name, r"^\d{8}-[0-9a-f]{12}\.png$")
        with open(os.path.join(self.dir, "assets", "t_first", name), "rb") as f:
            self.assertEqual(png(), f.read())
        last = self.card()["comments"][-1]
        self.assertEqual(f"The login page after the change\n\n![Login page](assets/t_first/{name})", last["text"])
        self.assertEqual("claude@alexdemo", last["by"])

    def test_details_appends_to_the_description_and_alt_is_cleaned(self):
        before = self.card().get("details", "")
        r = self.run_kt("attach", "t_first", self.img, "--details", "--alt", "a [bad]\nalt")
        self.assertEqual(0, r.returncode, r.stderr)
        details = self.card()["details"]
        self.assertTrue(details.startswith(before.rstrip()))
        self.assertRegex(details, r"!\[a  bad  alt\]\(assets/t_first/\d{8}-[0-9a-f]{12}\.png\)$")

    def test_the_same_image_twice_is_one_file(self):
        self.run_kt("attach", "t_first", self.img); self.run_kt("attach", "t_first", self.img)
        self.assertEqual(1, len(self.assets()))

    def test_refuses_what_is_not_an_image_or_too_big(self):
        n = len(self.card().get("comments", []))
        fake = os.path.join(self.tmp.name, "x.png")
        for body in (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', b"<html></html>", b"\x89PN"):
            with open(fake, "wb") as f:
                f.write(body)
            r = self.run_kt("attach", "t_first", fake)
            self.assertNotEqual(0, r.returncode); self.assertIn("only PNG, JPEG, GIF or WebP", r.stderr)
        with open(fake, "wb") as f:
            f.write(png() + b"\x00" * (2 * 1024 * 1024))
        r = self.run_kt("attach", "t_first", fake)
        self.assertNotEqual(0, r.returncode); self.assertIn("over 2 MB", r.stderr)
        self.assertEqual([], self.assets())
        self.assertEqual(n, len(self.card().get("comments", [])), "a refused attach adds no comment")

    def test_image_kind_reads_the_bytes(self):
        self.assertEqual("png", keeptrack.image_kind(png()))
        self.assertEqual("jpg", keeptrack.image_kind(b"\xff\xd8\xff\xe0rest"))
        self.assertEqual("gif", keeptrack.image_kind(b"GIF89a..."))
        self.assertEqual("webp", keeptrack.image_kind(b"RIFF\x00\x00\x00\x00WEBPVP8 "))
        self.assertEqual("", keeptrack.image_kind(b"<svg"))

    def test_assets_are_never_read_as_board_files(self):
        self.run_kt("attach", "t_first", self.img)
        self.assertFalse(keeptrack._wanted_rel("assets/t_first/x.png"))
        r = self.run_kt("doctor")
        self.assertNotIn("assets", r.stdout + r.stderr)

    def test_attach_strips_metadata(self):
        exif = b"Exif\x00\x00GPS-51.5074,-0.1278 OwnerName"
        app1 = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
        jpeg = b"\xff\xd8" + app1 + b"\xff\xdb\x00\x03\x00" + b"\xff\xda\x00\x02" + b"scan-data\xff\xd9"
        path = os.path.join(self.tmp.name, "photo.jpg")
        with open(path, "wb") as f:
            f.write(jpeg)
        r = self.run_kt("attach", "t_first", path)
        self.assertEqual(0, r.returncode, r.stderr)
        [name] = self.assets()
        with open(os.path.join(self.dir, "assets", "t_first", name), "rb") as f:
            saved = f.read()
        self.assertNotIn(b"GPS", saved); self.assertNotIn(b"Exif", saved)
        self.assertEqual(b"\xff\xd8\xff\xdb\x00\x03\x00\xff\xda\x00\x02scan-data\xff\xd9", saved, "everything else kept, in order")

    def test_strip_png_and_webp_metadata(self):
        ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        p = png()
        tagged = p[:-12] + ch(b"tEXt", b"Author\x00Jo Bloggs") + ch(b"eXIf", b"MM\x00*GPS") + p[-12:]
        self.assertEqual(p, keeptrack.strip_image_metadata(tagged, "png"))
        vp8x = b"VP8X" + (10).to_bytes(4, "little") + bytes([0x0C]) + b"\x00" * 9
        img = b"VP8L" + (5).to_bytes(4, "little") + b"/abcd" + b"\x00"
        ex = b"EXIF" + (4).to_bytes(4, "little") + b"GPS!"
        body = vp8x + img + ex
        webp = b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + body
        out = keeptrack.strip_image_metadata(webp, "webp")
        self.assertNotIn(b"GPS!", out); self.assertEqual("webp", keeptrack.image_kind(out))
        self.assertEqual(len(out) - 8, int.from_bytes(out[4:8], "little"), "the RIFF size matches")
        self.assertEqual(0, out[20] & 0x0C, "the EXIF and XMP flags are cleared")
        with self.assertRaises(ValueError):
            keeptrack.strip_image_metadata(p[:20], "png")

    def test_strip_gif_comments_and_xmp_and_jpeg_trailers(self):
        gif = (b"GIF89a" + b"\x01\x00\x01\x00\x80\x00\x00" + b"\x00\x00\x00\xff\xff\xff"      # header, screen, 2-colour table
               + b"\x21\xfe\x0bOWNER-SECRET"[:3] + b"\x0bOWNER-SECRE\x00"[1:]                 # placeholder, replaced below
               )
        comment = b"\x21\xfe" + bytes([12]) + b"OWNER-SECRET" + b"\x00"
        xmp = b"\x21\xff\x0bXMP DataXMP" + bytes([7]) + b"GPS=1,2" + b"\x00"
        loop = b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
        frame = b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00" + b"\x02\x02\x44\x01\x00"
        head = b"GIF89a" + b"\x01\x00\x01\x00\x80\x00\x00" + b"\x00\x00\x00\xff\xff\xff"
        tagged = head + comment + xmp + loop + frame + b"\x3b"
        out = keeptrack.strip_image_metadata(tagged, "gif")
        self.assertEqual(head + loop + frame + b"\x3b", out, "the animation loop and the frame stay")
        with self.assertRaises(ValueError):
            keeptrack.strip_image_metadata(head + b"\x21\xfe\x05ab", "gif")
        jpeg = b"\xff\xd8\xff\xdb\x00\x03\x00\xff\xda\x00\x02scan\xff\xd9" + b"\xff\xd8\xff\xe1\x00\x08Exif\x00\x00\xff\xd9TRAILER-GPS"
        self.assertEqual(b"\xff\xd8\xff\xdb\x00\x03\x00\xff\xda\x00\x02scan\xff\xd9", keeptrack.strip_image_metadata(jpeg, "jpg"),
                         "a second image or a vendor trailer after the end of the image is dropped")

    def test_orientation_is_kept_alone(self):
        """A phone photo's Orientation survives (so it is not saved sideways); GPS and the rest do not."""
        def exif(turn, extra=b"GPS-51.5"):
            # little-endian TIFF: IFD0 with Orientation and one more (ASCII) tag
            ifd = (2).to_bytes(2, "little") + b"\x12\x01\x03\x00\x01\x00\x00\x00" + turn.to_bytes(2, "little") + b"\x00\x00" \
                + b"\x0e\x01\x02\x00" + len(extra).to_bytes(4, "little") + (8 + 2 + 24 + 4).to_bytes(4, "little") + b"\x00\x00\x00\x00"
            return b"II*\x00\x08\x00\x00\x00" + ifd + extra
        tiff = exif(6)
        self.assertEqual(6, keeptrack.tiff_orientation(tiff)); self.assertEqual(1, keeptrack.tiff_orientation(b"junk"))
        body = b"Exif\x00\x00" + tiff
        jpeg = b"\xff\xd8\xff\xe1" + (len(body) + 2).to_bytes(2, "big") + body + b"\xff\xff\xdb\x00\x03\x00\xff\xda\x00\x02scan\xff\xd9"
        out = keeptrack.strip_image_metadata(jpeg, "jpg")   # (the 0xff 0xff before DQT is a fill byte)
        self.assertNotIn(b"GPS", out)
        self.assertEqual(b"\xff\xd8\xff\xe1", out[:4]); self.assertEqual(6, keeptrack.tiff_orientation(out[12:4 + int.from_bytes(out[4:6], "big")]))
        self.assertTrue(out.endswith(b"\xff\xdb\x00\x03\x00\xff\xda\x00\x02scan\xff\xd9"))
        plain = b"\xff\xd8\xff\xe1" + (len(b"Exif\x00\x00" + exif(1)) + 2).to_bytes(2, "big") + b"Exif\x00\x00" + exif(1) + b"\xff\xda\x00\x02s\xff\xd9"
        self.assertEqual(b"\xff\xd8\xff\xda\x00\x02s\xff\xd9", keeptrack.strip_image_metadata(plain, "jpg"), "upright: no EXIF at all")
        ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        p = png(); tagged = p[:-12] + ch(b"eXIf", exif(8)) + p[-12:]
        out = keeptrack.strip_image_metadata(tagged, "png")
        self.assertNotIn(b"GPS", out); self.assertIn(b"eXIf", out); self.assertEqual(p[:-12], out[:len(p) - 12])
        i = out.index(b"eXIf"); n = int.from_bytes(out[i - 4:i], "big")
        self.assertEqual(8, keeptrack.tiff_orientation(out[i + 4:i + 4 + n]))
        self.assertEqual(zlib.crc32(out[i:i + 4 + n]) & 0xFFFFFFFF, int.from_bytes(out[i + 4 + n:i + 8 + n], "big"), "a valid CRC")

    def test_proxy_403_switches_to_git_and_saves_again(self):
        """In a sandbox whose proxy refuses API writes (403 ... proxy), save_asset switches WRITE to git, reads the board
        again and saves through that mode (here a local board stands in for the git clone)."""
        calls = []
        old = (keeptrack.gh, keeptrack.load, keeptrack.WRITE, keeptrack.FILE)
        try:
            keeptrack.WRITE = "auto"; keeptrack.FILE = self.file; keeptrack._BOARD_STATES.clear()
            keeptrack.gh = lambda *a, **k: (calls.append(a) or (1, json.dumps({"message": "Blocked by the egress proxy"}), "HTTP 403"))
            keeptrack.load = lambda: ({}, {"mode": "local"})
            keeptrack.save_asset("assets/t_first/20261022-abcdefabcdef.png", png(), "Image: #1", {"mode": "api"})
            self.assertEqual("git", keeptrack.WRITE)
            self.assertEqual(1, len(calls))
            self.assertTrue(os.path.exists(os.path.join(self.dir, "assets", "t_first", "20261022-abcdefabcdef.png")))
        finally:
            keeptrack.gh, keeptrack.load, keeptrack.WRITE, keeptrack.FILE = old; keeptrack._BOARD_STATES.clear()

    def test_help_lists_attach(self):
        self.assertIn("attach", self.run_kt("help", "checklists-comments").stdout)


class Docs(unittest.TestCase):
    def test_kit_is_v92_with_upgrade_notes_and_changelog(self):
        self.assertGreaterEqual(keeptrack.KIT_VERSION, 92)   # the exact version is asserted by the newest tests/test_kit_v*.py
        with open(os.path.join(KIT, "UPGRADING.md"), encoding="utf-8") as f:
            v92 = f.read().split("### v92 (schema 4)", 1)[1].split("### v91", 1)[0]
        for words in ("kit-update", "attach", "assets/", "No migration", "2 MB"):
            self.assertIn(words, v92)
        with open(os.path.join(REPO, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("Kit v92", f.read())


if __name__ == "__main__":
    unittest.main()
