"""Извлекает палитру макета, усредняя по областям (устойчиво к границам)."""

from __future__ import annotations

import sys
from collections import Counter

from PIL import Image

path = sys.argv[1]
image = Image.open(path).convert("RGB")
width, height = image.size
print(f"Размер: {width}x{height}")


def area(name: str, left: int, top: int, right: int, bottom: int,
         *, saturation: bool = False) -> None:
    """Усредняет область и показывает самый частый цвет в ней.

    saturation=True отбирает только насыщенные пиксели — так находятся
    цвета кнопок и ссылок, не смешиваясь с белым фоном вокруг.
    """
    box = image.crop((left, top, right, bottom))
    pixels = list(box.get_flattened_data()) if hasattr(box, "get_flattened_data") \
        else list(box.getdata())

    if saturation:
        def vivid(px: tuple[int, int, int]) -> bool:
            mx, mn = max(px), min(px)
            return mx - mn > 60
        filtered = [px for px in pixels if vivid(px)]
        if filtered:
            pixels = filtered

    avg = tuple(sum(channel) // len(pixels) for channel in zip(*pixels))
    common = Counter(pixels).most_common(1)[0][0]
    note = " (только насыщенные)" if saturation else ""
    print(f"  {name:<32} среднее #{avg[0]:02x}{avg[1]:02x}{avg[2]:02x}"
          f"   частое #{common[0]:02x}{common[1]:02x}{common[2]:02x}{note}")


print("\n=== Фоны ===")
area("страница (правый низ)", 900, 860, 1000, 900)
area("сайдбар", 20, 380, 200, 430)
area("карточка таблицы", 600, 440, 900, 460)
area("drop-зона внутри", 500, 200, 900, 240)

print("\n=== Акценты (насыщенные пиксели) ===")
area("кнопка Add Collaborator", 1180, 80, 1340, 115, saturation=True)
area("ссылка Click here", 690, 265, 775, 282, saturation=True)
area("Edit (синий)", 1285, 515, 1315, 535, saturation=True)
area("Delete (красный)", 1245, 515, 1282, 535, saturation=True)
area("счётчик Home 10", 235, 178, 265, 198, saturation=True)
area("бейдж 81 Total", 480, 378, 520, 394, saturation=True)

print("\n=== Границы ===")
area("рамка drop-зоны", 315, 296, 322, 302)
area("разделитель под заголовком", 340, 143, 1300, 146)
area("рамка строки", 340, 632, 1300, 634)

print("\n=== Текст ===")
area("заголовок", 322, 88, 580, 108, saturation=True)
