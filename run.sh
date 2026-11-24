#!/bin/sh
# Runs a Python file in the repository's environment, from the repository root,
# with KATO's own logging silenced.
#   KATO_REPO   a checkout of https://github.com/sevakavakians/kato (required)
ROOT=$(cd "$(dirname "$0")" && pwd)
: "${KATO_REPO:?set KATO_REPO to a checkout of github.com/sevakavakians/kato}"
cd "$ROOT" && LOG_LEVEL=ERROR PYTHONPATH="$ROOT" "$ROOT/.venv/bin/python" "$@" 2>&1 \
  | grep -v "^INFO\|^DEBUG\|^WARNING\|RapidFuzz\|^\*\*\*"
