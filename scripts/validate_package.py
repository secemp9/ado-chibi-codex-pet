#!/usr/bin/env python3
"""Validate the installable Ado Codex pet package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PET_DIR = ROOT / "pet" / "ado"
MANIFEST_PATH = PET_DIR / "pet.json"
ATLAS_PATH = PET_DIR / "spritesheet.webp"
CHECKSUM_PATH = ROOT / "SHA256SUMS"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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

    with Image.open(ATLAS_PATH) as image:
        if image.format != "WEBP":
            raise SystemExit(f"expected WebP atlas, found {image.format}")
        if image.size != (1536, 2288):
            raise SystemExit(f"expected 1536x2288 atlas, found {image.size[0]}x{image.size[1]}")
        if "A" not in image.getbands():
            raise SystemExit("atlas does not contain an alpha channel")
        alpha = image.getchannel("A")
        if alpha.getextrema() == (255, 255):
            raise SystemExit("atlas has no transparent pixels")

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

    print("Ado Codex pet package validation passed")


if __name__ == "__main__":
    main()

