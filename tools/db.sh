#!/usr/bin/env bash
#
# Run an administrative action inside the deployed auth Lambda.
#
# Aurora is not publicly accessible (infra/rds.tf sets no publicly_accessible on
# the instance), so the only compute that can reach it is a Lambda in the VPC.
# Authorisation is lambda:InvokeFunction -- real AWS credentials -- rather than a
# shared secret on a Function URL whose authorization_type is NONE.
#
# Invocation is SYNCHRONOUS on purpose: an async invoke that fails delivers its
# payload to the DLQ (infra/lambda.tf:42), and seed payloads carry a password.
set -euo pipefail

ACTION="${1:-}"
case "$ACTION" in
    migrate|seed|db-current) ;;
    *) echo "usage: tools/db.sh {migrate|seed|db-current} [json-options]" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OPTIONS="${2:-{\}}"

# shellcheck disable=SC1091
[ -f "$ROOT/ENVIRONMENT.config" ] && source "$ROOT/ENVIRONMENT.config"
: "${PARTICIPANT_ID:?PARTICIPANT_ID not set -- run ./bin/setup-participant.sh}"
: "${PROJECT_NAME:=coding-workshop}"

"$ROOT/tools/verify-sync.sh" >/dev/null || {
    echo "FATAL: vendored acme_core is stale; 'make sync' then redeploy before running $ACTION" >&2
    exit 1
}

FN="${PROJECT_NAME}-auth-${PARTICIPANT_ID}"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

echo "invoking $FN action=$ACTION"
aws lambda invoke \
    --function-name "$FN" \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"source\":\"acme.admin.v1\",\"action\":\"$ACTION\",\"options\":$OPTIONS}" \
    "$OUT" >/dev/null
cat "$OUT"; echo
