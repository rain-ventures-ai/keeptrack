"""Regressions for image review follow-ups (private-tasks t_sh4ypf9u09)."""
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'board', 'kit'))
import keeptrack


def segment(marker, body):
    return bytes([255, marker]) + (len(body) + 2).to_bytes(2, 'big') + body


class ImageReview(unittest.TestCase):
    def test_valid_highly_compressible_large_png_rasters_are_accepted(self):
        import struct
        import zlib
        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        # Valid non-interlaced 8-bit PNGs: each row has filter 0 followed by exactly width*channels samples.
        # Build zlib input a row at a time, keeping test allocation independent of the full raster size.
        for width, height, channels, colour in ((1920, 1080, 3, 2), (4000, 4000, 3, 2), (4095, 4096, 4, 6)):
            with self.subTest(width=width, height=height, channels=channels):
                row = b'\0' * (1 + width * channels)
                compressor = zlib.compressobj()
                pieces = [compressor.compress(row) for _ in range(height)]
                pixels = b''.join(pieces) + compressor.flush()
                self.assertLess(len(pixels) * 100, len(row) * height, 'exercise highly compressed valid raster data')
                header = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, colour, 0, 0, 0))
                # Consecutive IDAT chunks may split the one zlib stream anywhere, including before its header ends.
                payload = chunk(b'IDAT', pixels[:1]) + chunk(b'IDAT', pixels[1:17]) + chunk(b'IDAT', pixels[17:])
                clean = header + payload + chunk(b'IEND', b'')
                tagged = header + chunk(b'tEXt', b'Author\0SYNTHETIC-OWNER') + payload + chunk(b'IEND', b'')
                self.assertEqual(keeptrack.strip_image_metadata(clean, 'png'), clean)
                self.assertEqual(keeptrack.strip_image_metadata(tagged, 'png'), clean)

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

    def test_png_preserves_default_pixels_but_drops_animation_and_private_metadata(self):
        import struct
        import zlib
        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        head = b'\x89PNG\r\n\x1a\n'
        ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        control = lambda seq: struct.pack('>IIIIIHHBB', seq, 1, 1, 0, 0, 1, 10, 0, 0)
        frames = (ihdr + chunk(b'acTL', struct.pack('>II', 2, 0)) + chunk(b'fcTL', control(0))
                  + chunk(b'IDAT', zlib.compress(b'\0\x11\x22\x33')) + chunk(b'fcTL', control(1))
                  + chunk(b'fdAT', struct.pack('>I', 2) + zlib.compress(b'\0\x33\x22\x11')) + chunk(b'IEND', b''))
        private = b''.join(chunk(kind, b'AUTHOR') for kind in (b'vpAg', b'caBX', b'iCCP', b'tIME', b'tEXt'))
        self.assertEqual(head + ihdr + chunk(b'IDAT', zlib.compress(b'\0\x11\x22\x33')) + chunk(b'IEND', b''), keeptrack.strip_image_metadata(head + private + frames, 'png'))
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
        unknown = b'\x21\xff\x0bPRIVATE-AUT\x06AUTHOR\0' + b'\x21\x01\x0c' + b'\0' * 12 + b'\x06AUTHOR\0'
        loop = b'\x21\xff\x0bNETSCAPE2.0\x03\x01\0\0\0'
        frame = b'\x2c\0\0\0\0\x01\0\x01\0\0\x02\x02\x44\x01\0'
        self.assertEqual(head + loop + frame + b'\x3b', keeptrack.strip_image_metadata(head + unknown + loop + frame + b'\x3b', 'gif'))

    def test_apng_streams_are_always_dropped_including_sequenced_plaintext_or_compressed_tails(self):
        import struct
        import zlib
        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        head = b'\x89PNG\r\n\x1a\n'
        ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        raw = b'\0\x11\x22\x33'
        pixels = chunk(b'IDAT', zlib.compress(raw))
        end = chunk(b'IEND', b'')
        control = lambda seq: struct.pack('>IIIIIHHBB', seq, 1, 1, 0, 0, 1, 10, 0, 0)
        orphan = chunk(b'fdAT', b'HIDDEN-AUTHOR') + chunk(b'fcTL', b'PRIVATE-LOCATION')
        self.assertEqual(head + ihdr + pixels + end, keeptrack.strip_image_metadata(head + ihdr + pixels + orphan + end, 'png'))
        for stream in (b'PRIVATE-NON-ZLIB-FRAME', zlib.compress(raw) + b'PRIVATE-TRAILER'):
            animation = (chunk(b'acTL', struct.pack('>II', 2, 0)) + chunk(b'fcTL', control(0))
                         + pixels + chunk(b'fcTL', control(1)) + chunk(b'fdAT', struct.pack('>I', 2) + stream))
            out = keeptrack.strip_image_metadata(head + ihdr + animation + end, 'png')
            self.assertEqual(head + ihdr + pixels + end, out)
            self.assertNotIn(b'PRIVATE', out)

    def test_png_rejects_ignored_zlib_tails_incomplete_streams_and_expansion(self):
        import struct
        import zlib
        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        head = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        stream = zlib.compress(b'\0\x11\x22\x33')
        for data in (stream + b'PRIVATE-TRAILER', stream[:-1], zlib.compress(b'x' * (64 * 1024 * 1024 + 1))):
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(head + chunk(b'IDAT', data) + chunk(b'IEND', b''), 'png')
        split = head + chunk(b'IDAT', stream[:3]) + chunk(b'IDAT', stream[3:]) + chunk(b'IEND', b'')
        self.assertEqual(split, keeptrack.strip_image_metadata(split, 'png'))

    def test_png_validates_exact_scanlines_including_adam7_and_packed_samples(self):
        import struct
        import zlib
        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        def image(raw, width=1, height=1, depth=8, colour=2, interlace=0):
            return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, colour, 0, 0, interlace))
                    + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
        for raw in (b'\0\x11\x22\x33PRIVATE', b'\0\x11', b'\x05\x11\x22\x33'):
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(image(raw), 'png')
        # An 8x8 one-bit greyscale Adam7 image: seven passes have 1,1,1,2,2,4,4 rows,
        # each containing a filter byte and a single packed sample byte.
        adam7 = image(b'\0\x55' * 15, 8, 8, 1, 0, 1)
        self.assertEqual(adam7, keeptrack.strip_image_metadata(adam7, 'png'))
        for delta in (-1, 1):
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(image(b'\0\x55' * (15 + delta), 8, 8, 1, 0, 1), 'png')
        tiny = image(b'\0\x80', 1, 1, 1, 0)
        self.assertEqual(tiny, keeptrack.strip_image_metadata(tiny, 'png'))
        many = tiny[:-12] + chunk(b'IDAT', b'') * 4097 + tiny[-12:]
        with self.assertRaises(ValueError):
            keeptrack.strip_image_metadata(many, 'png')

    def test_gif_graphics_control_targets_removed_text_not_following_image(self):
        head = bytes.fromhex('47494638396101000100800000000000ffffff')
        frame = bytes.fromhex('2c0000000001000100000202440100')
        control = bytes.fromhex('21f9040107000000')
        text = b'\x21\x01\x0c' + b'\0' * 12 + b'\x01A\0'
        comment = b'\x21\xfe\x01A\0'
        for extension, expected in ((text, b''), (comment, control)):
            self.assertEqual(head + expected + frame + b'\x3b', keeptrack.strip_image_metadata(head + control + extension + frame + b'\x3b', 'gif'))

    def test_jpeg_and_gif_parser_budgets(self):
        with self.assertRaisesRegex(ValueError, 'too many JPEG'):
            keeptrack.strip_image_metadata(b'\xff\xd8' + segment(221, b'\0\1') * 4097 + b'\xff\xd9', 'jpg')
        head = bytes.fromhex('47494638396101000100800000000000ffffff')
        frame = bytes.fromhex('2c0000000001000100000202440100')
        loop = bytes.fromhex('21ff0b4e45545343415045322e300301000000')
        for body in (loop * 4097, frame * 513, b'\x21\xfe' + b'\x01A' * 131073 + b'\0'):
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(head + body + b'\x3b', 'gif')

    def test_webp_rejects_duplicate_empty_and_excessive_chunks_before_retaining_them(self):
        def ch(kind, data):
            return kind + len(data).to_bytes(4, 'little') + data + (b'\0' if len(data) % 2 else b'')
        animation = ch(b'VP8X', b'\x02' + b'\0' * 9) + ch(b'ANIM', b'\0' * 6)
        frames = ch(b'ANMF', b'\0' * 16 + ch(b'VP8L', b'x')) * 513
        for body in (ch(b'VP8 ', b''), ch(b'VP8 ', b'x') + ch(b'VP8L', b'x'), ch(b'JUNK', b'') * 4097, animation + frames):
            image = b'RIFF' + (len(body) + 4).to_bytes(4, 'little') + b'WEBP' + body
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(image, 'webp')

    def test_webp_animation_requires_control_and_nonempty_pixel_frames(self):
        def chunk(kind, body):
            return kind + len(body).to_bytes(4, 'little') + body + (b'\0' if len(body) % 2 else b'')
        def riff(body):
            return b'RIFF' + (len(body) + 4).to_bytes(4, 'little') + b'WEBP' + body
        header = chunk(b'VP8X', bytes([2]) + b'\0' * 9)
        for body in (header, header + chunk(b'ANIM', b'\0' * 6), header + chunk(b'ANIM', b'\0' * 6) + chunk(b'ANMF', b'\0' * 16)):
            with self.assertRaises(ValueError):
                keeptrack.strip_image_metadata(riff(body), 'webp')
