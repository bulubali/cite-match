#!/usr/bin/env bash
set -euo pipefail
target= force=0 dry_run=0 uninstall=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) target="${2:-}"; shift 2;;
    --force) force=1; shift;;
    --dry-run) dry_run=1; shift;;
    --uninstall) uninstall=1; shift;;
    *) echo "Unknown argument: $1" >&2; exit 1;;
  esac
done
[[ "$target" == codex || "$target" == claude || "$target" == both ]] || { echo "Missing --target codex|claude|both." >&2; exit 1; }
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source="$repo_root/skill/SKILL.md"
[[ -f "$source" ]] || { echo "Skill source not found: $source" >&2; exit 1; }
grep -Eq '^name:[[:space:]]*cite-match[[:space:]]*$' "$source" || { echo "Invalid Skill name metadata." >&2; exit 1; }
grep -Eq '^description:' "$source" || { echo "Missing Skill description metadata." >&2; exit 1; }
echo "Detected platform: $(uname -s)"
echo "CiteMatch repository: $repo_root"
[[ -f "$repo_root/requirements.txt" ]] && echo "requirements.txt: PASS" || echo "requirements.txt: MISSING"
command -v python3 >/dev/null && echo "Dependency python3: PASS" || echo "Dependency python3: MISSING / MANUAL ACTION"
command -v pandoc >/dev/null && echo "Dependency pandoc: PASS" || echo "Dependency pandoc: MISSING / MANUAL ACTION"
command -v pandoc-crossref >/dev/null && echo "Dependency pandoc-crossref: PASS" || echo "Dependency pandoc-crossref: OPTIONAL / MANUAL ACTION"
names=() paths=()
if [[ "$target" == codex || "$target" == both ]]; then names+=(Codex); paths+=("$HOME/.agents/skills/cite-match/SKILL.md"); fi
if [[ "$target" == claude || "$target" == both ]]; then names+=(Claude); paths+=("$HOME/.claude/skills/cite-match/SKILL.md"); fi
rendered="$(sed "s|<PROJECT_ROOT>|$repo_root|g" "$source")"
for i in "${!names[@]}"; do
  name="${names[$i]}"; dest="${paths[$i]}"; dir="$(dirname "$dest")"; status="Not installed"
  if [[ -f "$dest" ]]; then current="$(cat "$dest")"; [[ "$current" == "$rendered" ]] && status="Already installed" || status="Update candidate"; fi
  echo "$name: $status -> $dest"
  (( dry_run )) && continue
  if (( uninstall )); then
    [[ -f "$dest" ]] || continue
    [[ "$(cat "$dest")" == "$rendered" ]] || { echo "Refusing uninstall: $dest is not installer-owned." >&2; exit 1; }
    rm -f -- "$dest"; rmdir --ignore-fail-on-non-empty "$dir" 2>/dev/null || true; echo "$name: Uninstalled"; continue
  fi
  [[ "$status" == "Already installed" ]] && continue
  if [[ "$status" == "Update candidate" && "$force" -ne 1 ]]; then echo "$name: Not overwritten (use --force to update)."; continue; fi
  mkdir -p -- "$dir"
  if [[ "$status" == "Update candidate" ]]; then cp -p -- "$dest" "$dest.backup-$(date +%Y%m%d%H%M%S)"; fi
  tmp="$dest.tmp.$$"; printf '%s\n' "$rendered" > "$tmp"; mv -f -- "$tmp" "$dest"; echo "$name: Installed -> $dest"
done
(( dry_run || uninstall )) || echo "Use /skills or /cite-match; reload or restart if not discovered."
