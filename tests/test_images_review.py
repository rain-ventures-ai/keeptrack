"""Regressions for image review follow-ups (private-tasks t_sh4ypf9u09)."""
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'board', 'kit'))
import keeptrack


def segment(marker, body):
    return bytes([255, marker]) + (len(body) + 2).to_bytes(2, 'big') + body


class ImageReview(unittest.TestCase):
    def test_progressive_jpeg_filters_metadata_between_scans_without_truncating_tables(self):
        first = segment(218, b'') + b'scan\xff\x00\xd9\xff\xd0bytes'
        table = segment(196, b'table\xff\xd9more')
        second = segment(218, b'') + b'second\xff\xd9'
        secret = segment(225, b'Exif\0\0GPS') + segment(237, b'IPTC') + segment(254, b'owner')
        image = b'\xff\xd8' + first + secret + table + second
        self.assertEqual(b'\xff\xd8' + first + table + second,
                         keeptrack.strip_image_metadata(image + b'trailer', 'jpg'))
        for malformed in (image[:-1], b'\xff\xd8' + segment(218, b'') + b'scan\xff'):
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(malformed, 'jpg')

    def test_webp_stops_at_riff_boundary_and_rejects_partial_chunks(self):
        def riff(body):
            return b'RIFF' + (len(body) + 4).to_bytes(4, 'little') + b'WEBP' + body
        image = riff(b'VP8 \x02\0\0\0ab')
        self.assertEqual(image, keeptrack.strip_image_metadata(image + b'EXIF\x04\0\0\0GPS!', 'webp'))
        for malformed in (image[:-1], riff(b'VP8 \x03\0\0\0abc'), riff(b'x')):
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(malformed, 'webp')

    def test_jpeg_application_allowlist_drops_provenance_author_and_thumbnails(self):
        pixels = segment(218, b'') + b'pixels\xff\xd9'
        metadata = b''.join(segment(m, b'AUTHOR-LOCATION') for m in range(0xe0, 0xf0))
        image = b'\xff\xd8' + metadata + pixels
        self.assertEqual(b'\xff\xd8' + pixels, keeptrack.strip_image_metadata(image, 'jpg'))
        jfif = b'JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x01\x01AUTHOR-THUMBNAIL'
        adobe = b'Adobe\x00\x64\x00\x00\x00\x00\x02AUTHOR'
        tagged = b'\xff\xd8' + segment(0xe0, jfif) + segment(0xee, adobe) + pixels
        out = keeptrack.strip_image_metadata(tagged, 'jpg')
        self.assertNotIn(b'AUTHOR', out)
        self.assertIn(b'JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00', out)
        self.assertIn(segment(0xee, adobe[:12]), out)

    def test_png_preserves_pixels_and_animation_but_drops_unknown_or_profile_metadata(self):
        import struct
        import zlib
        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        head = b'\x89PNG\r\n\x1a\n'
        frames = chunk(b'acTL', b'\0' * 8) + chunk(b'fcTL', b'\0' * 26) + chunk(b'IDAT', b'pixels') + chunk(b'fdAT', b'frame2') + chunk(b'IEND', b'')
        private = b''.join(chunk(kind, b'AUTHOR') for kind in (b'vpAg', b'caBX', b'iCCP', b'tIME', b'tEXt'))
        self.assertEqual(head + frames, keeptrack.strip_image_metadata(head + private + frames, 'png'))
        with self.assertRaises(ValueError):
            keeptrack.strip_image_metadata(head + chunk(b'AUTH', b'AUTHOR') + frames, 'png')

    def test_webp_sanitises_top_level_and_nested_frame_chunks(self):
        def chunk(kind, body):
            return kind + len(body).to_bytes(4, 'little') + body + (b'\0' if len(body) % 2 else b'')
        def riff(body):
            return b'RIFF' + (len(body) + 4).to_bytes(4, 'little') + b'WEBP' + body
        frame_pixels = chunk(b'VP8L', b'\x2fpixels')
        frame = b'\0' * 16 + frame_pixels + chunk(b'AUTH', b'FRAME-AUTHOR')
        body = chunk(b'VP8X', bytes([0x2e]) + b'\0' * 9) + chunk(b'ANIM', b'\0' * 6) + chunk(b'ANMF', frame)
        body += chunk(b'ICCP', b'PROFILE-AUTHOR') + chunk(b'AUTH', b'AUTHOR')
        out = keeptrack.strip_image_metadata(riff(body), 'webp')
        expected = chunk(b'VP8X', bytes([2]) + b'\0' * 9) + chunk(b'ANIM', b'\0' * 6) + chunk(b'ANMF', b'\0' * 16 + frame_pixels)
        self.assertEqual(riff(expected), out)
        self.assertNotIn(b'AUTHOR', out)

    def test_gif_keeps_loop_but_drops_unrecognised_application_extensions(self):
        head = b'GIF89a' + b'\x01\0\x01\0\x80\0\0' + b'\0\0\0\xff\xff\xff'
        unknown = b'\x21\xff\x0bPRIVATE-AUT\x06AUTHOR\0'
        loop = b'\x21\xff\x0bNETSCAPE2.0\x03\x01\0\0\0'
        frame = b'\x2c\0\0\0\0\x01\0\x01\0\0\x02\x02\x44\x01\0'
        self.assertEqual(head + loop + frame + b'\x3b', keeptrack.strip_image_metadata(head + unknown + loop + frame + b'\x3b', 'gif'))
