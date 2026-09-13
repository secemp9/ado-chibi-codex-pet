#!/usr/bin/env python3
"""Validate the installable Ado Codex pet package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageSequence


ROOT = Path(__file__).resolve().parents[1]
PET_DIR = ROOT / "pet" / "ado"
MANIFEST_PATH = PET_DIR / "pet.json"
ATLAS_PATH = PET_DIR / "spritesheet.webp"
CHECKSUM_PATH = ROOT / "SHA256SUMS"
PREVIEW_DIR = ROOT / "previews"
CELL_WIDTH = 192
CELL_HEIGHT = 208
PREVIEW_ALPHA_CUTOFF = 96
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


def component_mask(alpha: Image.Image, cutoff: int) -> bytes:
    components = connected_components(alpha, cutoff)
    if not components:
        return bytes(alpha.width * alpha.height)
    primary = max(components, key=len)
    mask = bytearray(alpha.width * alpha.height)
    # Prediction: the primary sprite mask contains exactly the largest atlas component.
    for pixel_index in primary:
        mask[pixel_index] = 255
    return bytes(mask)


def main() -> None:
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

    # Prediction: each used standard atlas cell has one primary sprite and no detached
    # component large enough to be a visible cross-slot remnant.
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

            if state == "idle" and column in {3, 4}:
                green_fringe = sum(
                    1
                    for red, green, blue, alpha_value in cell.getdata()
                    if alpha_value
                    and green > max(red * 1.5, blue * 1.12)
                    and green > 45
                )
                if green_fringe:
                    raise SystemExit(
                        f"idle atlas cell {column} retains {green_fringe} green-fringe pixels"
                    )

    # Prediction: all nine GIFs match their source-cell primary masks, timings, and transparency.
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
                expected_mask = component_mask(
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
                        f"{state} frame {frame_number} differs from its primary atlas mask "
                        f"at {mismatched_mask_pixels} pixels"
                    )

                output_components = connected_components(rgba.getchannel("A"), 1)
                if len(output_components) != 1:
                    raise SystemExit(
                        f"{state} frame {frame_number} has {len(output_components)} visible components"
                    )

                visible_key_green = sum(
                    1
                    for red, green, blue, alpha in rgba.getdata()
                    if alpha > 0 and red < 80 and green > 120 and blue < 80
                )
                if visible_key_green:
                    raise SystemExit(
                        f"{state} frame {frame_number} retains {visible_key_green} visible key-green pixels"
                    )

                if state == "idle" and frame_number in {3, 4}:
                    green_fringe = sum(
                        1
                        for red, green, blue, alpha_value in rgba.getdata()
                        if alpha_value
                        and green > max(red * 1.5, blue * 1.12)
                        and green > 45
                    )
                    if green_fringe:
                        raise SystemExit(
                            f"idle preview frame {frame_number} retains {green_fringe} green-fringe pixels"
                        )

    print("Ado Codex pet package and preview validation passed")


if __name__ == "__main__":
    main()
