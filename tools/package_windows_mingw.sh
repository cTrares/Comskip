#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
portable_dir="$repo_root/dist/ComSkip"
python_launcher="${1:-$repo_root/_temp/reproducible-build/python-dist/comskip-final.exe}"

required=(
  "$repo_root/comskip.exe"
  "$repo_root/comskip-gui.exe"
  "$python_launcher"
  "/mingw64/bin/ffmpeg.exe"
  "/mingw64/bin/ffprobe.exe"
)

for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "Required build output not found: $path" >&2
    exit 1
  fi
done

mkdir -p "$portable_dir"
cp -f "$repo_root/comskip.exe" "$portable_dir/comskip.exe"
cp -f "$repo_root/comskip-gui.exe" "$portable_dir/ComskipGUI.exe"
cp -f "$python_launcher" "$portable_dir/comskip-final.exe"
cp -f /mingw64/bin/ffmpeg.exe /mingw64/bin/ffprobe.exe "$portable_dir/"
cp -f "$repo_root/Makromodus-Sender.txt" "$portable_dir/"
cp -f "$repo_root/Schnellmodus-Sender.txt" "$portable_dir/"

declare -A seen=()
queue=(
  "$portable_dir/comskip.exe"
  "$portable_dir/ComskipGUI.exe"
  "$portable_dir/ffmpeg.exe"
  "$portable_dir/ffprobe.exe"
)

while ((${#queue[@]})); do
  current="${queue[0]}"
  queue=("${queue[@]:1}")

  while IFS= read -r dependency; do
    [[ "$dependency" == /mingw64/bin/*.dll ]] || continue
    [[ -z "${seen[$dependency]:-}" ]] || continue
    seen[$dependency]=1
    cp -f "$dependency" "$portable_dir/"
    queue+=("$dependency")
  done < <(ldd "$current" | awk '/=> \/mingw64\/bin\// {print $3} /^\/mingw64\/bin\// {print $1}')
done

echo "Portable runtime assembled at $portable_dir"
