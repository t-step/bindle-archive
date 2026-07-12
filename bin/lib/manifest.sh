#!/usr/bin/env bash
#
# manifest.sh — shared reader for install-manifest.tsv (generated from
# capabilities.json by bin/check-inventory.py --emit-manifest). Sourced by
# install.sh and doctor.sh so the type->destination mapping and the item list
# live in exactly one place.
#
# each_manifest_item REPO_ROOT CALLBACK
#   For every data row, invokes:
#     CALLBACK PROVIDER CATEGORY NAME SRC_ABS DEST_REL
#   in file order. Skips the '#' banner and blank lines. SRC_ABS is
#   REPO_ROOT/<src_rel>; DEST_REL is relative to the provider home.
#   A missing manifest is a silent no-op (return 0).

each_manifest_item() {
  local repo_root="$1" cb="$2" manifest provider category name src_rel dest_rel
  manifest="$repo_root/install-manifest.tsv"
  [ -f "$manifest" ] || return 0
  while IFS=$'\t' read -r provider category name src_rel dest_rel; do
    case "$provider" in '' | '#'*) continue ;; esac
    "$cb" "$provider" "$category" "$name" "$repo_root/$src_rel" "$dest_rel"
  done <"$manifest"
}
