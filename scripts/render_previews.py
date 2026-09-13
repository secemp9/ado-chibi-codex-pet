#!/usr/bin/env python3
"""Render artifact-free GIF previews from the final cleaned Codex pet atlas."""

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


def connected_components(alpha: Image.Image) -> list[list[int]]:
    width, height = alpha.size
    data = alpha.tobytes()
    visited = bytearray(width * height)
    components: list[list[int]] = []

    # Prediction: every visible preview pixel belongs to one four-connected component.
    for start, value in enumerate(data):
        if value < ALPHA_CUTOFF or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            x = current % width
            neighbors = (
                current - 1 if x else -1,
                current + 1 if x + 1 < width else -1,
                current - width if current >= width else -1,
                current + width if current + width < width * height else -1,
            )
            for neighbor in neighbors:
                if neighbor >= 0 and data[neighbor] >= ALPHA_CUTOFF and not visited[neighbor]:
                    visited[neighbor] = 1
                    stack.append(neighbor)
        components.append(component)
    return components


def isolate_primary_sprite(source: Image.Image) -> Image.Image:
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A")
    components = connected_components(alpha)
    if not components:
        return rgba

    primary = max(components, key=len)
    primary_mask = Image.new("L", rgba.size, 0)
    mask_pixels = primary_mask.load()
    # Prediction: the largest thresholded component is Ado; smaller components are
    # cross-slot remnants and must never appear in a standalone animation frame.
    for pixel_index in primary:
        mask_pixels[pixel_index % rgba.width, pixel_index // rgba.width] = 255
    rgba.putalpha(primary_mask)
    return rgba


def shift_green_fringe_to_teal(source: Image.Image) -> Image.Image:
    rgba = source.convert("RGBA")
    pixels = rgba.load()
    # Prediction: the confirmed late-idle defect is the green-dominant subset of
    # the hair edge, so a blueward hue correction preserves the intended teal hair.
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha and green > max(red * 1.5, blue * 1.12) and green > 45:
                pixels[x, y] = (
                    red,
                    green,
                    max(blue, min(255, round(green * 1.35))),
                    alpha,
                )
    return rgba


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
            if state == "idle" and column in {3, 4}:
                frame = shift_green_fringe_to_teal(frame)
            rgba_frames.append(isolate_primary_sprite(frame))

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
