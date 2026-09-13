# Changelog

## v1.0.4

- Corrected unintended growth in the three middle crouching poses of the `failed` animation by using stable-slot extraction from the same coherent generated row.
- Preserved the first four failed poses, final face-down pose, and every other atlas cell byte-for-byte.
- Regenerated the failed GIF and full contact sheet, then passed deterministic validation and independent playback review across both affected transitions.

## v1.0.3

- Regenerated the complete `idle`, `failed`, and `waiting` rows with separated poses, visible gutters, and safe cell margins instead of attempting to mask contaminated cells.
- Removed the remaining green-key edge spill from preserved animation and look-direction artwork, then cleaned the regenerated rows against a contrasting yellow key.
- Regenerated all nine README GIFs and the contact sheet directly from the packaged atlas, with no preview-only silhouette isolation or color correction.
- Added a visually approved full-cell silhouette baseline, exact GIF-to-atlas mask comparison, detached-component checks, safe-margin checks, and independent green/yellow chroma validation.

## v1.0.2

- Removed 1,905 pixels belonging to verified detached cross-slot remnants in the `failed` and `waiting` atlas cells.
- Shifted 312 green-dominant pixels in the two affected late-idle cells back into Ado's established teal hair palette.
- Regenerated all nine README GIFs with one shared palette per animation and exactly one primary sprite component per frame.
- Strengthened validation to compare every GIF alpha mask against its matching cleaned atlas cell and to reject detached components, timing drift, or the repaired idle fringe returning.

## v1.0.1

- Regenerated all nine README GIFs directly from the final despilled v2 atlas.
- Added preview validation for dimensions, frame counts, transparency, and visible key-green pixels.
- Added a deterministic preview-rendering script for future releases.
- Kept the installable pet runtime identical to v1.0.0.

## v1.0.0

- Initial private release of the Ado chibi Codex pet.
