The 44-byte `still-4000px-lossless.webp` is a generated 4000×2 solid-colour (#336699) image, containing a simple VP8L chunk with no VP8X flags. It has no source photograph or embedded metadata. Generated with ImageMagick's lossless WebP encoder:

    magick -size 4000x2 xc:'#336699' -define webp:lossless=true -strip still-4000px-lossless.webp

The browser test adds a large unknown metadata chunk at runtime, then checks sanitisation and resizing of this still image.
