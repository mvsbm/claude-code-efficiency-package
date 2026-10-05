#!/usr/bin/env bash
set -euo pipefail
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/claude-code-efficiency-package"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export EFFICIENCY_STATE="${EFFICIENCY_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/claude-code-efficiency-package}"
if [[ -n "${EFFICIENCY_CONFIG:-}" ]]; then
  mkdir -p -m 700 "$EFFICIENCY_STATE"
  CONFIG_SNAPSHOT=$(mktemp "$EFFICIENCY_STATE/config-XXXXXX.json")
  python3 -m claude_code_efficiency.settings --config "$EFFICIENCY_CONFIG" --flat > "$CONFIG_SNAPSHOT"
  export EFFICIENCY_CONFIG="$CONFIG_SNAPSHOT"
  CONFIG_ENV=$(python3 -m claude_code_efficiency.settings --config "$EFFICIENCY_CONFIG" --export)
  while IFS='=' read -r key value; do
    [[ -v "$key" ]] || export "$key=$value"
  done <<< "$CONFIG_ENV"
  if [[ "${EFFICIENCY_REQUIRE_COMMIT:-0}" == 1 && -z "${EFFICIENCY_BASE_COMMIT:-}" ]]; then
    echo 'Completion guard requires explicit EFFICIENCY_BASE_COMMIT.' >&2; exit 2
  fi
fi
export SOL_ARCHIVE_DIR="$EFFICIENCY_STATE/archives"
export SOL_STATS_DIR="$EFFICIENCY_STATE/live"
export EFFICIENCY_PROFILE="${EFFICIENCY_PROFILE:-fused}"
CLAUDE="${EFFICIENCY_CLAUDE_BIN:-$(command -v claude || true)}"
[[ -n "$CLAUDE" ]] || { echo 'Install Claude Code or set EFFICIENCY_CLAUDE_BIN.' >&2; exit 2; }
MODEL="${EFFICIENCY_MODEL:-sonnet}"
# Session-level supported TTL choice, never a paid keepalive or history rewrite.
if [[ -n "${EFFICIENCY_CACHE_TTL:-}" ]]; then
  case "$EFFICIENCY_CACHE_TTL" in 5m|1h) export CLAUDE_CODE_PROMPT_CACHE_TTL="$EFFICIENCY_CACHE_TTL" ;; *) echo 'EFFICIENCY_CACHE_TTL must be 5m or 1h' >&2; exit 2 ;; esac
fi
# Opt-in full conversation logging; local files only, never an API proxy.
if [[ "${EFFICIENCY_ACCOUNTING:-0}" == 1 ]]; then
  if [[ "${EFFICIENCY_ACCOUNTING_SYNTHETIC:-0}" != 1 ]] && { [[ "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}" != https://api.anthropic.com && "${ANTHROPIC_BASE_URL:-}" != https://api.anthropic.com/ ]] || [[ "${CLAUDE_CODE_USE_BEDROCK:-0}" == 1 || "${CLAUDE_CODE_USE_VERTEX:-0}" == 1 || "${CLAUDE_CODE_USE_FOUNDRY:-0}" == 1 ]]; }; then
    echo 'Usage capture requires the direct Anthropic endpoint; other providers are not supported.' >&2; exit 2
  fi
  mkdir -p -m 700 "$EFFICIENCY_STATE"
  TRACE_DIR=$(mktemp -d "$EFFICIENCY_STATE/api-XXXXXXXX")
  export CLAUDE_CODE_ENABLE_TELEMETRY=1
  export OTEL_LOGS_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_TRACES_EXPORTER=none
  export EFFICIENCY_TRACE_DIR="$TRACE_DIR"
  python3 - "$TRACE_DIR" <<'PY'
import json, os, sys
from pathlib import Path
from urllib.parse import urlparse
(Path(sys.argv[1])/'accounting-provenance.json').write_text(json.dumps({'endpoint_host':urlparse(os.environ.get('ANTHROPIC_BASE_URL','https://api.anthropic.com')).hostname,'synthetic':os.environ.get('EFFICIENCY_ACCOUNTING_SYNTHETIC')=='1'}))
PY
  export OTEL_LOG_RAW_API_BODIES="file:$TRACE_DIR"
  printf 'Local API accounting archive (contains conversation/source): %s\n' "$TRACE_DIR" >&2
fi
# Preserve authentication, gateway, permissions and normal user/project settings.
case "$EFFICIENCY_PROFILE" in
  fused) TOOLS=Read,Glob,Grep,Bash ;;
  native) TOOLS=Read,Glob,Grep,Write,Edit,Bash ;;
  before) exec "$CLAUDE" --strict-mcp-config --model "$MODEL" --tools Read,Glob,Grep,Write,Edit,Bash "$@" ;;
  *) echo 'EFFICIENCY_PROFILE must be fused, native, or before' >&2; exit 2 ;;
esac
PROMPT="$(< "$ROOT/instructions.txt")"
if [[ "$EFFICIENCY_PROFILE" == native ]]; then
  PROMPT=${PROMPT/"Native Write/Edit are deliberately unavailable."/"Native Write/Edit are available; the fused helper is optional in this profile."}
fi
if [[ -n "${EFFICIENCY_CONFIG:-}" && "${EFFICIENCY_REGIONS:-1}" == 1 ]]; then
  PROMPT+=$'\n'"$(< "$ROOT/handles.txt")"
fi
exec "$CLAUDE" --strict-mcp-config --model "$MODEL" --tools "$TOOLS" --settings "$ROOT/hooks.json" --append-system-prompt "$PROMPT" "$@"
