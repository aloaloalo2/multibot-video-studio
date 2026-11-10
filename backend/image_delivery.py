"""Metadata-free PNG copies for user-facing episode folders; Studio keeps originals.

Copy encoded pixels and colour information verbatim. This removes container metadata,
including C2PA, EXIF and text, and does not remove marks encoded in the pixels.
"""
from pathlib import Path
import os
import struct
import tempfile
import zlib


SIGNATURE = b'\x89PNG\r\n\x1a\n'
# Rendering chunks only, including colour profiles, transparency and animated PNG.
RENDERING = frozenset((b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS', b'iCCP',
                       b'sRGB', b'gAMA', b'cHRM', b'cICP', b'mDCV', b'cLLI',
                       b'sBIT', b'bKGD', b'acTL', b'fcTL', b'fdAT'))


def clean_png(data: bytes) -> bytes:
    if not data.startswith(SIGNATURE):
        raise OSError('Не вдалося прочитати PNG для збереження')
    output = bytearray(SIGNATURE)
    offset, first, pixels = 8, True, False
    while offset + 12 <= len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            break
        kind = data[offset + 4:offset + 8]
        if first and (kind != b'IHDR' or size != 13):
            break
        if zlib.crc32(data[offset + 4:end - 4]) != struct.unpack_from('>I', data, end - 4)[0]:
            break
        if kind not in RENDERING and not kind[0] & 32:
            break  # Unsupported critical chunk: never publish a damaged copy.
        if kind in RENDERING:
            output.extend(data[offset:end])
        pixels |= kind == b'IDAT'
        if kind == b'IEND':
            if size or not pixels:
                break
            return bytes(output)  # Also discard any trailing metadata.
        first, offset = False, end
    raise OSError('Пошкоджений PNG не збережено в папку випуску')


def copy_png(source: Path, target: Path) -> None:
    """Atomically deliver a clean copy, leaving source and any previous output safe."""
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise OSError('Оригінал картинки має залишатися окремо від копії')
    cleaned = clean_png(source.read_bytes())
    stamp = source.stat()
    fd, name = tempfile.mkstemp(prefix='.' + target.name + '.', suffix='.tmp', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(cleaned)
        # An exported cover must not look like a newer hand-edited replacement
        # to thumbnail_gen.preview(), which imports such replacements into Studio.
        os.utime(temporary, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
