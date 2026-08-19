#!/usr/bin/env bash
# Run one of the two hosted models over a corpus. PAID: one API call per page.
#
#   ./run_cloud.sh claude --corpus real/pages --out out_real/claude
#   ./run_cloud.sh gpt    --corpus real/pages --out out_real/gpt
#
# KEY is sourced from ~/.secrets/ai.env

set -euo pipefail

PROVIDER="${1:-}"
shift || true
case "$PROVIDER" in
  claude|gpt) ;;
  *) echo "usage: $0 {claude|gpt} [--corpus DIR] [--out DIR] [--dpi N] [--only ID] [--limit N]" >&2
     exit 2 ;;
esac

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$HOME/.secrets/ai.env}"

if [ ! -r "$ENV_FILE" ]; then
  echo "ENV_FILE not readable: $ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

exec "$HERE/envs/cloud/bin/python" "$HERE/adapters/run_${PROVIDER}.py" "$@"
