#!/usr/bin/env bash
set -euo pipefail

force=false
if [[ "${1:-}" == "--force" ]]; then
  force=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: ./install.sh [--force]" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
package_dir="$script_dir/pet/ado"
codex_root="${CODEX_HOME:-${HOME}/.codex}"
target_dir="$codex_root/pets/ado"
checksum_file="$script_dir/SHA256SUMS"

expected_hash="$(awk '$2 == "pet/ado/spritesheet.webp" { print $1 }' "$checksum_file")"
if command -v sha256sum >/dev/null 2>&1; then
  actual_hash="$(sha256sum "$package_dir/spritesheet.webp" | awk '{ print $1 }')"
elif command -v shasum >/dev/null 2>&1; then
  actual_hash="$(shasum -a 256 "$package_dir/spritesheet.webp" | awk '{ print $1 }')"
else
  echo "A SHA-256 utility is required (sha256sum or shasum)." >&2
  exit 1
fi

if [[ -z "$expected_hash" || "$actual_hash" != "$expected_hash" ]]; then
  echo "Spritesheet checksum verification failed." >&2
  exit 1
fi

if [[ -e "$target_dir" ]]; then
  if [[ "$force" != true ]]; then
    echo "Ado is already installed at $target_dir" >&2
    echo "Run ./install.sh --force to back it up and replace it." >&2
    exit 1
  fi

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="$codex_root/pet-backups/ado.backup.$timestamp"
  mkdir -p "$(dirname -- "$backup_dir")"
  mv "$target_dir" "$backup_dir"
  echo "Backed up the previous installation to $backup_dir"
fi

mkdir -p "$target_dir"
cp "$package_dir/pet.json" "$package_dir/spritesheet.webp" "$target_dir/"

echo "Installed Ado at $target_dir"
echo "Open Codex > Settings > Pets > Refresh, then select Ado."

