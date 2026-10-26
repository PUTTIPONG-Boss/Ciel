"""Generate the PNG app icons (web/icons/icon-192.png, icon-512.png) with no dependencies.

    python scripts/make_icons.py
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"

BG = (5, 8, 7)
STOPS = [(0.0, (255, 251, 234)), (0.3, (255, 224, 138)), (0.65, (255, 154, 46)), (1.0, (122, 58, 6))]
RING = (233, 185, 73)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def gradient(t):
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            return lerp(c0, c1, (t - t0) / (t1 - t0))
    return STOPS[-1][1]


def pixel(x, y, size):
    # coordinates in a 64-unit space to match icon.svg
    u, v = x / size * 64, y / size * 64
    color = BG
    d = math.hypot(u - 32, v - 32)
    if abs(d - 25) < 0.9:  # ring
        color = lerp(BG, RING, 0.85)
    if d <= 18:  # orb
        g = math.hypot(u - (32 - 18 + 0.38 * 36), v - (32 - 18 + 0.32 * 36)) / (0.75 * 36)
        color = gradient(g)
    elif d < 19:  # anti-alias edge
        color = lerp(gradient(1.0), color, d - 18)
    return color


def write_png(path, size):
    rows = b"".join(b"\x00" + bytes(c for x in range(size) for c in pixel(x + 0.5, y + 0.5, size)) for y in range(size))
    chunk = lambda tag, data: struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        write_png(OUT / f"icon-{size}.png", size)
        print(f"wrote icon-{size}.png")
