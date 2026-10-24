# Synthetic JPEG parser fixtures

These 16 × 12 red-to-blue gradients contain no personal data. Generated with ImageMagick:

```sh
magick -size 16x12 gradient:red-blue -strip -quality 85 baseline-fill.jpg
magick -size 16x12 gradient:red-blue -strip -quality 85 -interlace Plane progressive-fill.jpg
```

Tests insert marker fill bytes immediately before the terminal EOI marker, then compare the sanitised scans with the original sanitised image. Both fixtures decode as real JPEGs; the second uses progressive scans.
