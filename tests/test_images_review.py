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
