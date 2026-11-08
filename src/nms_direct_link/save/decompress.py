"""Decode the LZ4 block stream that No Man's Sky uses for save*.hg files.

Layout (little-endian), repeated until end of file:
    u32 magic        = 0xFEEDA1E5
    u32 compressed   size of the LZ4 block that follows
    u32 decompressed size of that block (max 0x80000 = 512 KiB)
    u32 reserved
    bytes[compressed]

A file whose first byte is ``{`` is already plain JSON (older saves, or saves written by editors).
The decoded JSON is NUL-padded at the end; the padding is stripped.
"""

from __future__ import annotations

import struct

import lz4.block

MAGIC = 0xFEEDA1E5
HEADER = struct.Struct("<4I")
MAX_BLOCK = 0x80000


class SaveFormatError(ValueError):
    """The bytes are not a recognisable No Man's Sky save."""


def decompress_save(raw: bytes) -> bytes:
    """Return the JSON bytes of a save, whether it is LZ4-block compressed or plain."""
    if not raw:
        raise SaveFormatError("save file is empty")
    if raw[:1] == b"{":
        return raw.rstrip(b"\x00")
    out = bytearray()
    pos = 0
    n = len(raw)
    while pos + HEADER.size <= n:
        magic, csize, dsize, _reserved = HEADER.unpack_from(raw, pos)
        if magic != MAGIC:
            raise SaveFormatError(f"bad block magic {magic:#010x} at offset {pos}")
        if dsize == 0 or dsize > MAX_BLOCK:
            raise SaveFormatError(f"implausible block size {dsize} at offset {pos}")
        pos += HEADER.size
        chunk = raw[pos : pos + csize]
        if len(chunk) != csize:
            raise SaveFormatError("truncated save: block runs past end of file")
        out += lz4.block.decompress(chunk, uncompressed_size=dsize)
        pos += csize
    if pos != n:
        raise SaveFormatError(f"trailing {n - pos} bytes after last block")
    return bytes(out).rstrip(b"\x00")


def compress_save(data: bytes) -> bytes:
    """Inverse of :func:`decompress_save`. Used by tests to build synthetic fixtures."""
    out = bytearray()
    for start in range(0, len(data), MAX_BLOCK):
        block = data[start : start + MAX_BLOCK]
        comp = lz4.block.compress(block, store_size=False)
        out += HEADER.pack(MAGIC, len(comp), len(block), 0)
        out += comp
    return bytes(out)
