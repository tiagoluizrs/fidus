"""Gera os ícones do Fidus (sem dependências): anel externo (o chamado), anel ondulado interno (a voz) e um ponto.

Saídas em assets/: tray-dark.png (branco, para barra escura), tray-light.png (preto, para barra clara),
icon.png (256 px, colorido sobre fundo escuro) e icon.ico (16 a 256 px).
"""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets"
SS = 4  # supersampling


def coverage(px: float, py: float, size: int) -> float:
    """Cobertura (0..1) do símbolo no ponto (px, py) em coordenadas de [-1, 1]."""
    r = math.hypot(px, py)
    th = math.atan2(py, px)
    thick_out = 0.11 if size >= 24 else 0.16
    thick_in = 0.045 if size >= 24 else 0.09
    hit = abs(r - 0.80) < thick_out / 2  # anel externo
    wob = 0.50 * (1 + 0.05 * math.sin(4 * th)) if size >= 24 else 0.50  # anel ondulado interno
    hit = hit or abs(r - wob) < thick_in / 2
    hit = hit or r < (0.075 if size >= 24 else 0.11)  # ponto
    return 1.0 if hit else 0.0


def render(size: int, color_fn, background=None) -> bytes:
    rows = []
    n = size * SS
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            cov = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    px = ((x * SS + sx) / n) * 2 - 1
                    py = ((y * SS + sy) / n) * 2 - 1
                    cov += coverage(px, py, size)
            cov /= SS * SS
            r, g, b = color_fn(y / max(1, size - 1))
            if background:
                bg = background(x, y, size)
                a = bg[3] / 255
                out = [round(bg[i] * (1 - cov) + c * cov) for i, c in enumerate((r, g, b))] + [round(255 * (a + cov * (1 - a)))]
            else:
                out = [r, g, b, round(255 * cov)]
            row += bytes(out)
        rows.append(bytes(row))
    return png(size, size, b"".join(rows))


def png(w: int, h: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def gradient(t: float):
    stops = [(255, 106, 61), (255, 92, 158), (61, 139, 255)]  # laranja, rosa, azul (Alfred)
    t = min(max(t, 0), 1) * 2
    i = min(int(t), 1)
    f = t - i
    a, b = stops[i], stops[i + 1]
    return tuple(round(a[k] + (b[k] - a[k]) * f) for k in range(3))


def rounded_bg(x: int, y: int, size: int):
    r = size * 0.22
    cx = min(max(x, r), size - 1 - r)
    cy = min(max(y, r), size - 1 - r)
    inside = math.hypot(x - cx, y - cy) <= r
    return (10, 10, 11, 255) if inside else (0, 0, 0, 0)


def ico(images: dict[int, bytes]) -> bytes:
    head = struct.pack("<HHH", 0, 1, len(images))
    entries, blobs, offset = b"", b"", 6 + 16 * len(images)
    for size, data in images.items():
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return head + entries + blobs


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "tray-dark.png").write_bytes(render(32, lambda t: (255, 255, 255)))
    (OUT / "tray-light.png").write_bytes(render(32, lambda t: (10, 10, 11)))
    sizes = {s: render(s, gradient, rounded_bg) for s in (16, 24, 32, 48, 64, 128, 256)}
    (OUT / "icon.png").write_bytes(sizes[256])
    (OUT / "icon.ico").write_bytes(ico(sizes))
    print("ok:", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
