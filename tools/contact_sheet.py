"""Render local training images as labeled sheets for manual species review."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1] / "data" / "recognition"
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "contact-sheets"
OUTPUT.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader((ROOT / "sources.csv").open(encoding="utf-8")))

for species_id in sorted({row["image"].split("/")[0] for row in rows}):
    subset = [row for row in rows if row["image"].startswith(species_id + "/")]
    columns = 6
    cell_width, cell_height = 150, 148
    sheet = Image.new("RGB", (columns * cell_width, ((len(subset) + columns - 1) // columns) * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(subset):
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        with Image.open(ROOT / row["image"]) as source:
            image = ImageOps.fit(source.convert("RGB"), (cell_width - 8, cell_height - 28))
        sheet.paste(image, (x + 4, y + 4))
        draw.text((x + 5, y + cell_height - 20), Path(row["image"]).stem, fill="black")
    output = OUTPUT / f"{species_id}.jpg"
    sheet.save(output, quality=90)
    print(output)
