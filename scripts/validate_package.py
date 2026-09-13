#!/usr/bin/env python3
"""Validate the installable Ado Codex pet package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageFilter, ImageSequence


ROOT = Path(__file__).resolve().parents[1]
PET_DIR = ROOT / "pet" / "ado"
MANIFEST_PATH = PET_DIR / "pet.json"
ATLAS_PATH = PET_DIR / "spritesheet.webp"
CHECKSUM_PATH = ROOT / "SHA256SUMS"
PREVIEW_DIR = ROOT / "previews"
SILHOUETTE_BASELINE_PATH = ROOT / "qa" / "approved-silhouette-masks.json"
CELL_WIDTH = 192
CELL_HEIGHT = 208
PREVIEW_ALPHA_CUTOFF = 96
EDGE_MARGIN = 4
PREVIEW_ROWS = {
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def near_key_color(
    red: int,
    green: int,
    blue: int,
    key: tuple[int, int, int],
    threshold: int = 96,
) -> bool:
    return (
        (red - key[0]) ** 2
        + (green - key[1]) ** 2
        + (blue - key[2]) ** 2
        <= threshold**2
    )


def key_leak_count(image: Image.Image, key: tuple[int, int, int]) -> int:
    return sum(
        1
        for red, green, blue, alpha in image.convert("RGBA").getdata()
        if alpha > 16 and near_key_color(red, green, blue, key, threshold=36)
    )


def key_fringe_count(image: Image.Image, key: tuple[int, int, int]) -> int:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    visible = [value > 0 for value in alpha.getdata()]
    transparent = Image.new("L", alpha.size)
    transparent.putdata([255 if not value else 0 for value in visible])
    nearby_transparency = transparent.filter(ImageFilter.MaxFilter(5))
    return sum(
        alpha_value > 16
        and nearby > 0
        and near_key_color(red, green, blue, key, threshold=96)
        for (red, green, blue, _alpha), alpha_value, nearby in zip(
            rgba.getdata(), alpha.getdata(), nearby_transparency.getdata()
        )
    )


def connected_components(alpha: Image.Image, cutoff: int) -> list[list[int]]:
    width, height = alpha.size
    data = alpha.tobytes()
    visited = bytearray(width * height)
    components: list[list[int]] = []

    # Prediction: every pixel meeting the cutoff belongs to exactly one four-connected component.
    for start, value in enumerate(data):
        if value < cutoff or visited[start]:
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
                if neighbor >= 0 and data[neighbor] >= cutoff and not visited[neighbor]:
                    visited[neighbor] = 1
                    stack.append(neighbor)
        components.append(component)
    return components


def threshold_mask(alpha: Image.Image, cutoff: int) -> bytes:
    return bytes(255 if value >= cutoff else 0 for value in alpha.tobytes())


def mask_bbox(mask: bytes) -> list[int] | None:
    visible = [index for index, value in enumerate(mask) if value]
    if not visible:
        return None
    xs = [index % CELL_WIDTH for index in visible]
    ys = [index // CELL_WIDTH for index in visible]
    return [min(xs), min(ys), max(xs), max(ys)]


def standard_cell_records(atlas: Image.Image) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    # Prediction: the nine standard rows contain the exact 57 populated cells in PREVIEW_ROWS.
    for state, (row, durations) in PREVIEW_ROWS.items():
        for column in range(len(durations)):
            left = column * CELL_WIDTH
            top = row * CELL_HEIGHT
            cell = atlas.crop((left, top, left + CELL_WIDTH, top + CELL_HEIGHT))
            mask = threshold_mask(cell.getchannel("A"), PREVIEW_ALPHA_CUTOFF)
            records[f"{state}:{column}"] = {
                "row": row,
                "column": column,
                "visiblePixels": sum(1 for value in mask if value),
                "bbox": mask_bbox(mask),
                "maskSha256": sha256_bytes(mask),
            }
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-mask-baseline",
        action="store_true",
        help="write the visually approved standard-cell silhouette baseline and exit",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_manifest = {
        "id": "ado",
        "displayName": "Ado",
        "description": "A dramatic chibi singer pet with a mischievous streak and an expressive emotional range.",
        "spriteVersionNumber": 2,
        "spritesheetPath": "spritesheet.webp",
    }
    if manifest != expected_manifest:
        raise SystemExit("pet.json does not match the expected v2 manifest")

    with Image.open(ATLAS_PATH) as opened:
        if opened.format != "WEBP":
            raise SystemExit(f"expected WebP atlas, found {opened.format}")
        if opened.size != (1536, 2288):
            raise SystemExit(f"expected 1536x2288 atlas, found {opened.size[0]}x{opened.size[1]}")
        if "A" not in opened.getbands():
            raise SystemExit("atlas does not contain an alpha channel")
        alpha = opened.getchannel("A")
        if alpha.getextrema() == (255, 255):
            raise SystemExit("atlas has no transparent pixels")
        atlas = opened.convert("RGBA")

    if args.write_mask_baseline:
        baseline = {
            "schemaVersion": 1,
            "alphaCutoff": PREVIEW_ALPHA_CUTOFF,
            "purpose": "Visually approved standard-row masks; prevents connected or detached cross-slot bleed from returning.",
            "cells": standard_cell_records(atlas),
        }
        SILHOUETTE_BASELINE_PATH.write_text(
            json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {SILHOUETTE_BASELINE_PATH}")
        return

    expected_hashes: dict[str, str] = {}
    # Prediction: SHA256SUMS contains exactly the two runtime files named below.
    for line in CHECKSUM_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative_path = line.split(maxsplit=1)
        expected_hashes[relative_path] = digest

    expected_paths = {"pet/ado/pet.json", "pet/ado/spritesheet.webp"}
    if set(expected_hashes) != expected_paths:
        raise SystemExit("SHA256SUMS must list exactly the two runtime files")

    # Prediction: both packaged runtime files match their recorded release hashes.
    for relative_path, expected_hash in expected_hashes.items():
        actual_hash = sha256(ROOT / relative_path)
        if actual_hash != expected_hash:
            raise SystemExit(f"checksum mismatch for {relative_path}")

    baseline = json.loads(SILHOUETTE_BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline.get("alphaCutoff") != PREVIEW_ALPHA_CUTOFF:
        raise SystemExit("approved silhouette baseline uses the wrong alpha cutoff")
    expected_records = baseline.get("cells")
    actual_records = standard_cell_records(atlas)
    if expected_records != actual_records:
        changed = sorted(
            key
            for key in set(expected_records or {}) | set(actual_records)
            if (expected_records or {}).get(key) != actual_records.get(key)
        )
        raise SystemExit(
            "standard-cell silhouettes differ from the visually approved baseline: "
            + ", ".join(changed)
        )

    # Prediction: each used standard atlas cell has one complete sprite, four pixels
    # of safe outer clearance, and no visible green- or yellow-key contamination.
    for state, (row, durations) in PREVIEW_ROWS.items():
        for column in range(len(durations)):
            left = column * CELL_WIDTH
            top = row * CELL_HEIGHT
            cell = atlas.crop((left, top, left + CELL_WIDTH, top + CELL_HEIGHT))
            components = connected_components(cell.getchannel("A"), PREVIEW_ALPHA_CUTOFF)
            sizes = sorted((len(component) for component in components), reverse=True)
            visible_remnants = [size for size in sizes[1:] if size >= 8]
            if not sizes or visible_remnants:
                raise SystemExit(
                    f"{state} atlas cell {column} has detached visible components: {sizes}"
                )

            mask = threshold_mask(cell.getchannel("A"), PREVIEW_ALPHA_CUTOFF)
            edge_pixels = sum(
                1
                for index, value in enumerate(mask)
                if value
                and (
                    index % CELL_WIDTH < EDGE_MARGIN
                    or index % CELL_WIDTH >= CELL_WIDTH - EDGE_MARGIN
                    or index // CELL_WIDTH < EDGE_MARGIN
                    or index // CELL_WIDTH >= CELL_HEIGHT - EDGE_MARGIN
                )
            )
            if edge_pixels:
                raise SystemExit(
                    f"{state} atlas cell {column} has {edge_pixels} visible pixels inside the {EDGE_MARGIN}px safety margin"
                )

            green_leaks = key_leak_count(cell, (0, 255, 0))
            green_fringe = key_fringe_count(cell, (0, 255, 0))
            yellow_leaks = key_leak_count(cell, (255, 255, 0))
            yellow_fringe = key_fringe_count(cell, (255, 255, 0))
            if (
                green_leaks > 400
                or yellow_leaks > 400
                or green_fringe
                or yellow_fringe
            ):
                raise SystemExit(
                    f"{state} atlas cell {column} retains key-color contamination: "
                    f"green_leaks={green_leaks}, green_fringe={green_fringe}, "
                    f"yellow_leaks={yellow_leaks}, yellow_fringe={yellow_fringe}"
                )

    # Prediction: all nine GIFs reproduce their complete source-cell masks, timings,
    # and transparency without a preview-only cleanup hiding atlas defects.
    for state, (row, durations) in PREVIEW_ROWS.items():
        expected_count = len(durations)
        preview_path = PREVIEW_DIR / f"{state}.gif"
        with Image.open(preview_path) as preview:
            if preview.format != "GIF":
                raise SystemExit(f"expected GIF preview for {state}, found {preview.format}")
            if preview.n_frames != expected_count:
                raise SystemExit(
                    f"{state} preview needs {expected_count} frames, found {preview.n_frames}"
                )

            for frame_number, frame in enumerate(ImageSequence.Iterator(preview)):
                rgba = frame.convert("RGBA")
                if rgba.size != (CELL_WIDTH, CELL_HEIGHT):
                    raise SystemExit(
                        f"{state} frame {frame_number} must be 192x208, found {rgba.size}"
                    )
                if rgba.getchannel("A").getextrema()[0] != 0:
                    raise SystemExit(f"{state} frame {frame_number} has no transparent background")

                if frame.info.get("duration") != durations[frame_number]:
                    raise SystemExit(
                        f"{state} frame {frame_number} duration is {frame.info.get('duration')}ms; "
                        f"expected {durations[frame_number]}ms"
                    )

                left = frame_number * CELL_WIDTH
                top = row * CELL_HEIGHT
                source_cell = atlas.crop((left, top, left + CELL_WIDTH, top + CELL_HEIGHT))
                expected_mask = threshold_mask(
                    source_cell.getchannel("A"), PREVIEW_ALPHA_CUTOFF
                )
                actual_mask = bytes(
                    255 if value else 0 for value in rgba.getchannel("A").tobytes()
                )
                mismatched_mask_pixels = sum(
                    1
                    for expected, actual in zip(expected_mask, actual_mask)
                    if expected != actual
                )
                if mismatched_mask_pixels:
                    raise SystemExit(
                        f"{state} frame {frame_number} differs from its complete atlas mask "
                        f"at {mismatched_mask_pixels} pixels"
                    )

                output_components = connected_components(rgba.getchannel("A"), 1)
                output_sizes = sorted(
                    (len(component) for component in output_components), reverse=True
                )
                visible_output_remnants = [
                    size for size in output_sizes[1:] if size >= 8
                ]
                if not output_sizes or visible_output_remnants:
                    raise SystemExit(
                        f"{state} frame {frame_number} has detached visible components: {output_sizes}"
                    )

                visible_key_green = key_leak_count(
                    rgba, (0, 255, 0)
                ) + key_fringe_count(rgba, (0, 255, 0))
                if visible_key_green:
                    raise SystemExit(
                        f"{state} frame {frame_number} retains {visible_key_green} visible key-green pixels"
                    )

                visible_key_yellow = key_leak_count(
                    rgba, (255, 255, 0)
                ) + key_fringe_count(rgba, (255, 255, 0))
                if visible_key_yellow:
                    raise SystemExit(
                        f"{state} frame {frame_number} retains {visible_key_yellow} visible key-yellow pixels"
                    )

    print("Ado Codex pet package and preview validation passed")


if __name__ == "__main__":
    main()
