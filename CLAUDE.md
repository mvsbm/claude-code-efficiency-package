# Claude Code instructions for this repository

## Goal

Install this package in an isolated location and test whether it reduces **total reported token usage per correctly completed task**. Do not assume savings. A smaller prompt, fewer bytes, or fewer tool calls alone is not evidence of a successful task-level saving.

## Project commands

```bash
PYTHONPATH=src python3 -m unittest discover -s tests/unit -v
bash -n scripts/launcher.sh
python3 scripts/build_config_schema.py && git diff --exit-code -- config/schema.json
```

The native integration check uses a fake API; it verifies protocol behavior, **not** token savings.

## Install without changing the user's normal setup

Prefer a temporary install and a temporary Claude config directory. Do not edit `~/.claude` or replace the user's globally installed Claude Code unless asked.

```bash
tmp="$(mktemp -d)"
python3 scripts/install.py --data-home "$tmp/data" --bin-dir "$tmp/bin"
CLAUDE_BIN="$(command -v claude)" # Or point to one pinned fresh CLI install; use the same binary in both arms.
"$CLAUDE_BIN" --version
```

The package launcher supports `EFFICIENCY_PROFILE=before` (control: bypass package hooks/guidance) and `EFFICIENCY_PROFILE=fused` (treatment). Use the **same Claude Code executable, model, task prompt, limits, and fresh workspace snapshot** in both arms.


## Paired token-usage test

Only proceed after the Claude Code handshake succeeds:

1. Use at least four small, independently reset coding tasks with explicit tests or an equivalent objective correctness check. Give each arm the same prompt and identical source snapshot.
2. Run both `before` and `fused` for each task. Counterbalance order across pairs; use the same model/server settings and per-run turn/time limits. Do not force a target number of tool calls.
3. Give each arm a fresh session and worktree. Keep task results, traces, and raw logs outside this repository (raw API bodies contain full prompts/source).
4. For local raw usage capture, set `EFFICIENCY_ACCOUNTING=1` and `EFFICIENCY_ACCOUNTING_SYNTHETIC=1`. The latter marks non-Anthropic usage as synthetic; it does **not** make it Anthropic billing data. Check `archive_consistent`, `issues`, and unpaired requests. Missing counters or incomplete traces invalidate that run.

With the local environment above and the isolated install, invoke each arm from its own pristine task worktree. Use a unique state/config directory per arm so sessions and traces cannot leak across runs:

```bash
run_arm() {
  profile="$1"; task="$2"; worktree="$3"; prompt="$4"
  ( cd "$worktree" && \
    EFFICIENCY_PROFILE="$profile" \
    EFFICIENCY_MODEL="$ANTHROPIC_MODEL" \
    EFFICIENCY_CLAUDE_BIN="$CLAUDE_BIN" \
    EFFICIENCY_STATE="$tmp/state/$task-$profile" \
    EFFICIENCY_ACCOUNTING=1 EFFICIENCY_ACCOUNTING_SYNTHETIC=1 \
    CLAUDE_CONFIG_DIR="$tmp/claude-config/$task-$profile" \
    "$tmp/bin/claude-code-efficiency" --print --output-format json \
      --max-turns 8 --no-session-persistence "$prompt"
  )
}
# Example: run_arm before task-01 /tmp/task-01-before 'Implement ...'
#          run_arm fused  task-01 /tmp/task-01-fused  'Implement ...'
```

Keep the exact prompt and initial files identical between the two worktrees. The launcher prints each raw accounting archive path; parse it with `PYTHONPATH="$tmp/data/claude-code-efficiency-package" python3 -m claude_code_efficiency.accounting "$TRACE_DIR"`. Require `archive_consistent: true` and no issues; keep those raw archives out of Git.
5. Sum the response `usage` counters for every attempt: `input_tokens + cache_read_input_tokens + cache_creation_input_tokens + output_tokens`. Do not add the optional cache-TTL breakdown again. Include failed attempts whenever their usage is captured; if any failed, unpaired, or in-flight attempt has no usage, mark the run incomplete rather than dropping it or assuming zero. Divide the complete token total by correctly completed, timely tasks. If either arm fails the task or usage is incomplete, report the pair as inconclusive—not a saving.
6. Report per-pair counts, correctness, retries/turns, and latency. A small pilot is directional only; do not claim a general reduction from a single task or fake-API test.

The `accounting` module reports captured response token counters, not an invoice or guaranteed complete session total. Keep local experiment artifacts private and out of Git; commit only code/docs changes the user requests.
