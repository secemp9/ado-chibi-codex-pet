#!/usr/bin/env python3
"""Remove detached cell remnants and the two confirmed idle green fringes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_SIZE = (1536, 2288)
COMPONENT_ALPHA_CUTOFF = 96
MIN_REMNANT_PIXELS = 8
USED_FRAME_COUNTS = (6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)
IDLE_GREEN_REPAIR_COLUMNS = {3, 4}


def report_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def connected_components(alpha: Image.Image) -> list[list[int]]:
    width, height = alpha.size
    data = alpha.tobytes()
    visited = bytearray(width * height)
    components: list[list[int]] = []

    # Prediction: every nonzero alpha pixel belongs to exactly one four-connected component.
    for start, value in enumerate(data):
        if value < COMPONENT_ALPHA_CUTOFF or visited[start]:
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
                if (
                    neighbor >= 0
                    and data[neighbor] >= COMPONENT_ALPHA_CUTOFF
                    and not visited[neighbor]
                ):
                    visited[neighbor] = 1
                    stack.append(neighbor)
        components.append(component)
    return components


def remove_detached_components(cell: Image.Image) -> tuple[Image.Image, list[int], int]:
    rgba = cell.convert("RGBA")
    alpha = rgba.getchannel("A")
    components = connected_components(alpha)
    if len(components) <= 1:
        return rgba, [], 0

    primary = max(components, key=len)
    detached = [
        component
        for component in components
        if component is not primary and len(component) >= MIN_REMNANT_PIXELS
    ]
    if not detached:
        return rgba, [], 0

    primary_mask = Image.new("L", rgba.size, 0)
    primary_pixels = primary_mask.load()
    # Prediction: the largest component is Ado and must remain untouched.
    for pixel_index in primary:
        primary_pixels[pixel_index % rgba.width, pixel_index // rgba.width] = 255

    detached_mask = Image.new("L", rgba.size, 0)
    detached_pixels = detached_mask.load()
    # Prediction: every qualifying smaller component is a detached cross-slot remnant.
    for component in detached:
        for pixel_index in component:
            detached_pixels[pixel_index % rgba.width, pixel_index // rgba.width] = 255
    detached_band = detached_mask.filter(ImageFilter.MaxFilter(3))

    source = list(rgba.getdata())
    primary_data = primary_mask.tobytes()
    detached_data = detached_band.tobytes()
    repaired = []
    removed_pixels = 0
    # Prediction: only each detached island and its one-pixel antialias fringe are cleared.
    for index, pixel in enumerate(source):
        red, green, blue, alpha_value = pixel
        remove = bool(detached_data[index]) and not bool(primary_data[index])
        if alpha_value and remove:
            repaired.append((0, 0, 0, 0))
            removed_pixels += 1
        else:
            repaired.append((red, green, blue, alpha_value))
    rgba.putdata(repaired)
    return rgba, sorted((len(component) for component in detached), reverse=True), removed_pixels


def shift_green_fringe_to_teal(cell: Image.Image) -> tuple[Image.Image, int]:
    rgba = cell.convert("RGBA")
    pixels = rgba.load()
    changed = 0
    # Prediction: the two confirmed idle defects are green-dominant hair-edge pixels;
    # shifting only those pixels blueward restores the established navy-to-teal palette.
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
                changed += 1
    return rgba, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--atlas",
        default=str(ROOT / "pet" / "ado" / "spritesheet.webp"),
        help="source 1536x2288 v2 atlas",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "pet" / "ado" / "spritesheet.webp"),
        help="lossless WebP output path",
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "qa" / "artifact-repair.json"),
        help="JSON report path",
    )
    args = parser.parse_args()

    atlas_path = Path(args.atlas).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve()
    with Image.open(atlas_path) as opened:
        atlas = opened.convert("RGBA")
    if atlas.size != ATLAS_SIZE:
        raise SystemExit(f"expected {ATLAS_SIZE[0]}x{ATLAS_SIZE[1]} atlas, found {atlas.size}")

    repaired_atlas = atlas.copy()
    component_repairs = []
    green_repairs = []
    # Prediction: only used v2 cells are processed; unused cells remain byte-for-byte transparent.
    for row, frame_count in enumerate(USED_FRAME_COUNTS):
        for column in range(frame_count):
            left = column * CELL_WIDTH
            top = row * CELL_HEIGHT
            box = (left, top, left + CELL_WIDTH, top + CELL_HEIGHT)
            cell, detached_sizes, removed_pixels = remove_detached_components(atlas.crop(box))
            if row == 0 and column in IDLE_GREEN_REPAIR_COLUMNS:
                cell, changed_pixels = shift_green_fringe_to_teal(cell)
                green_repairs.append({"row": row, "column": column, "changed_pixels": changed_pixels})
            if detached_sizes:
                component_repairs.append(
                    {
                        "row": row,
                        "column": column,
                        "detached_component_sizes": detached_sizes,
                        "removed_pixels": removed_pixels,
                    }
                )
            repaired_atlas.paste(cell, (left, top))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_name(f".{output_path.name}.tmp.webp")
    repaired_atlas.save(temporary_output, "WEBP", lossless=True, method=6, exact=True)
    temporary_output.replace(output_path)

    report = {
        "ok": True,
        "input": report_path(atlas_path),
        "output": report_path(output_path),
        "component_alpha_cutoff": COMPONENT_ALPHA_CUTOFF,
        "component_repairs": component_repairs,
        "green_repairs": green_repairs,
        "total_removed_pixels": sum(item["removed_pixels"] for item in component_repairs),
        "total_recolored_pixels": sum(item["changed_pixels"] for item in green_repairs),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
