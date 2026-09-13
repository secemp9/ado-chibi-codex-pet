#!/usr/bin/env python3
"""Render transparent GIF previews from the final cleaned Codex pet atlas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_SIZE = (1536, 2288)
TRANSPARENT_INDEX = 255
ALPHA_CUTOFF = 96
ROW_DURATIONS = {
    "idle": (0, [280, 110, 110, 140, 140, 320]),
    "running-right": (1, [120, 120, 120, 120, 120, 120, 120, 220]),
    "running-left": (2, [120, 120, 120, 120, 120, 120, 120, 220]),
    "waving": (3, [140, 140, 140, 280]),
    "jumping": (4, [140, 140, 140, 140, 280]),
    "failed": (5, [140, 140, 140, 140, 140, 140, 140, 240]),
    "waiting": (6, [150, 150, 150, 150, 150, 260]),
    "running": (7, [120, 120, 120, 120, 120, 220]),
    "review": (8, [150, 150, 150, 150, 150, 280]),
}


def make_shared_palette(frames: list[Image.Image]) -> Image.Image:
    palette_source = Image.new("RGB", (CELL_WIDTH * len(frames), CELL_HEIGHT), (20, 22, 42))
    # Prediction: one palette learned from the entire row preserves navy/cyan colors
    # consistently and reserves index 255 for transparency in every frame.
    for index, frame in enumerate(frames):
        rgba = frame.convert("RGBA")
        matte = Image.new("RGB", rgba.size, (20, 22, 42))
        matte.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
        palette_source.paste(matte, (index * CELL_WIDTH, 0))
    return palette_source.quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )


def gif_frame(source: Image.Image, palette: Image.Image) -> Image.Image:
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A")
    transparent_mask = alpha.point(lambda value: 255 if value < ALPHA_CUTOFF else 0)

    indexed = rgba.convert("RGB").quantize(
        palette=palette,
        dither=Image.Dither.FLOYDSTEINBERG,
    )
    indexed.paste(TRANSPARENT_INDEX, mask=transparent_mask)
    indexed.info["transparency"] = TRANSPARENT_INDEX
    indexed.info["disposal"] = 2
    return indexed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--atlas",
        default=str(ROOT / "pet" / "ado" / "spritesheet.webp"),
        help="final cleaned 1536x2288 v2 atlas",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "previews"),
        help="directory receiving the nine GIF previews",
    )
    args = parser.parse_args()

    atlas_path = Path(args.atlas).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(atlas_path) as opened:
        atlas = opened.convert("RGBA")
    if atlas.size != ATLAS_SIZE:
        raise SystemExit(f"expected {ATLAS_SIZE[0]}x{ATLAS_SIZE[1]} atlas, found {atlas.size}")

    rendered = []
    # Prediction: rows 0-8 contain the exact populated frame counts encoded in ROW_DURATIONS.
    for state, (row, durations) in ROW_DURATIONS.items():
        rgba_frames = []
        for column in range(len(durations)):
            left = column * CELL_WIDTH
            top = row * CELL_HEIGHT
            frame = atlas.crop((left, top, left + CELL_WIDTH, top + CELL_HEIGHT))
            rgba_frames.append(frame)

        palette = make_shared_palette(rgba_frames)
        frames = [gif_frame(frame, palette) for frame in rgba_frames]

        output = output_dir / f"{state}.gif"
        frames[0].save(
            output,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
            transparency=TRANSPARENT_INDEX,
            background=TRANSPARENT_INDEX,
            optimize=False,
        )
        rendered.append({"state": state, "frames": len(frames), "path": str(output)})

    print(json.dumps({"ok": True, "atlas": str(atlas_path), "previews": rendered}, indent=2))


if __name__ == "__main__":
    main()
