#!/usr/bin/env bash
#
# Fail if any service's vendored acme_core differs from the source of truth.
# Guards the failure mode where bin/deploy-backend.sh (plain `terraform apply`)
# is run directly and ships stale or absent shared code.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SRC="$ROOT/backend/_shared/acme_core"
status=0

shopt -s nullglob
for req in "$ROOT"/backend/*/requirements.txt; do
    svc_dir="$(dirname "$req")"
    svc="$(basename "$svc_dir")"
    case "$svc" in _*|.*) continue ;; esac

    if [ ! -d "$svc_dir/acme_core" ]; then
        echo "  STALE: backend/$svc has no vendored acme_core -- run 'make sync'" >&2
        status=1
        continue
    fi
    # _build_stamp.py is regenerated every sync, so exclude it from the comparison.
    if ! diff -rq --exclude='__pycache__' --exclude='_build_stamp.py' \
            "$SRC" "$svc_dir/acme_core" >/dev/null 2>&1; then
        echo "  STALE: backend/$svc/acme_core differs from _shared -- run 'make sync'" >&2
        status=1
    else
        echo "  ok: backend/$svc/acme_core matches _shared"
    fi
done
shopt -u nullglob

exit "$status"
