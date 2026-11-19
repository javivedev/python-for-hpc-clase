#!/usr/bin/env bash
set -euo pipefail

version=v0.51.0
case "$(uname -s):$(uname -m)" in
    Linux:x86_64)
        arch=amd64
        checksum=c3752ad51a5a4015a113819c4eeb6e55a4d0e4b8e652494797532f6fc8161dd7
        ;;
    Linux:aarch64)
        arch=arm64
        checksum=3ee05c82e5f9198928a4e86133608ba6a2c10a2244d6a7789e820f78319d640c
        ;;
    *)
        printf 'Este instalador requiere Linux x86_64 o ARM64.\n' >&2
        exit 1
        ;;
esac

archive="k9s_Linux_${arch}.tar.gz"
release="https://github.com/derailed/k9s/releases/download/${version}"
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT

curl -L --fail --silent --show-error --retry 2 --max-time 120 \
    --output "$work_dir/$archive" "$release/$archive"
printf '%s  %s\n' "$checksum" "$work_dir/$archive" | sha256sum --check
tar -xzf "$work_dir/$archive" -C "$work_dir" -- k9s
install -d "$HOME/.local/bin"
install -m 0755 "$work_dir/k9s" "$HOME/.local/bin/k9s"
"$HOME/.local/bin/k9s" version
