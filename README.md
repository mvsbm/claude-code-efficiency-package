# Claude Code Efficiency Package

Small, stdlib-only helpers and supported native Claude Code hooks. No MCP server, model-backed reducer, credential changes, or permission bypass. Requires Python 3.10+, Bash, Git, and Claude Code on Linux.

**Token or cost savings are not guaranteed.** Fewer bytes or output tokens can still increase retries, cache traffic, latency, or failures. Optimize cost per correctly completed task, not isolated payload size. Region handles are opt-in/advisory tools, not automatic context compression.

## Repository layout

- `src/claude_code_efficiency/` — importable runtime package
- `scripts/` — installer, launcher, and config-schema generator
- `config/` — schema and example configurations
- `templates/` — generated Claude hook settings and prompt guidance
- `tests/unit/`, `tests/integration/` — tests and deterministic fake-API check

## Install and launch

```bash
python3 scripts/install.py
claude-code-efficiency
```

Installs runtime files to `~/.local/share/claude-code-efficiency-package` and a launcher to `~/.local/bin`. Does not edit Claude's global settings or authentication. Private session state is stored separately under `~/.local/state/claude-code-efficiency-package`.

Profiles:

```bash
EFFICIENCY_PROFILE=fused claude-code-efficiency  # Read, Glob, Grep, Bash
EFFICIENCY_PROFILE=native claude-code-efficiency # also normal Write/Edit
EFFICIENCY_PROFILE=before claude-code-efficiency # omit package hooks/guidance
```

The fused profile reserves source mutations for the helper. Its shell guard is a workflow constraint, **not a sandbox**. Normal Claude Bash permissions still apply. `before` is a launcher bypass profile, not an assertion of literal vanilla equivalence. `EFFICIENCY_MODEL` and `EFFICIENCY_CLAUDE_BIN` override the normal model alias/executable. The launcher excludes MCP.

## Exact changes and validation

The launcher adds the installed package to `PYTHONPATH`. A helper command can apply a strict patch and run known validation in one permission-checked Bash call:

```bash
python3 -m claude_code_efficiency.operations \
  apply-patch --patch - --then-run 'python3 -m unittest' --timeout 120 <<'PATCH'
*** Begin Patch
*** Update File: example.py
@@
-def answer():
-    return 41
+def answer():
+    return 42
*** End Patch
PATCH
```

Each hunk matches original content exactly once. No line numbers, fuzzy matching, deletes, renames, or no-newline markers. Add File refuses existing targets. JSON `apply --spec -` supports exact replacements and multiple separate `then_run` entries. Files remain changed if validation fails; review the retained output rather than assuming success.

Large selective changes can use `region-read --file FILE --start N --end M`, then `region-replace region_ID --replacement - --then-run 'known check'`. Handles bind the entire original file hash. Lookup, receipts, retries, and replacement code all count toward cost.

Inputs are content-addressed as `input_ID`. `repair-input ID --old 'unique bad fragment' --new 'replacement'` does not mutate source. Reapply the returned ID explicitly.

For structured checker output, use `--output-format ruff-json` with a standalone `ruff check . --output-format=json`, or `pyright-json` with `pyright --outputjson`. Never combine plain test output with structured JSON in one structured stream. Omitted details remain available through `check-recall CHECK_ID --stream stdout --offset 0 --limit 8192`.

## Runtime configuration

```bash
EFFICIENCY_CONFIG=/absolute/path/config.json claude-code-efficiency
PYTHONPATH=src python3 -m claude_code_efficiency.settings --config config/examples/native.json
```

Partial overrides are validated against `config/schema.json`; unknown/retired keys fail. Explicit environment overrides take precedence over JSON, then defaults. The launcher freezes a private resolved snapshot per session. Runtime keys:

- `profile`: `fused`, `native`, `before`.
- `regions.enabled`: enable revision-bound helper operations.
- `workflow.read_reuse_hints`: advisory hints for unchanged file revisions.
- `completion.require_commit`, `completion.max_reminders`: opt-in guard, 1–3 reminders.
- `checks.compact`, `checks.max_diagnostics`, `checks.max_bytes`.

Old experimental configs containing `documents`, `benchmark`, `objective`, or `workflow.structured` are intentionally rejected. Create a runtime-only config rather than silently ignoring retired options. Permissions, original archives, and failure preservation are not optimizer knobs.

The completion guard requires an explicit base commit:

```bash
EFFICIENCY_REQUIRE_COMMIT=1 EFFICIENCY_BASE_COMMIT="$(git rev-parse HEAD)" \
  claude-code-efficiency
```

Reminders are bounded; an unresolved violation remains unresolved after the limit. The guard does not establish semantic correctness.

## Local API usage capture

`EFFICIENCY_ACCOUNTING=1` opts into local raw API request/response body logging for the direct Anthropic endpoint. These files contain private conversation and source content; do not publish them. Exporters are disabled.

The report copies token counters from captured successful response bodies and flags missing provenance, malformed records, and unpaired requests. Those per-response counters come from Anthropic's API `usage` object; `archive_consistent` means only that no problems were found in the files inspected, not proof that every session request was captured. Failed or in-flight requests may be missing. The automated integration test uses a fake API, so reconcile a live capture before relying on session-wide completeness. It is **not** a billing record and does not estimate cost. Verify charges against Anthropic's own billing records. Usage capture is disabled by default. Manual `EFFICIENCY_CACHE_TTL=5m|1h` is available; no priming or keepalives.

## Verify

```bash
PYTHONPATH=src python3 -m unittest discover -s tests/unit -v
bash -n scripts/launcher.sh
python3 scripts/build_config_schema.py
# Optional isolated native integration test; fake API, no model generation:
tmp="$(mktemp -d)"
python3 scripts/install.py --data-home "$tmp/data" --bin-dir "$tmp/bin"
XDG_DATA_HOME="$tmp/data" PYTHONPATH=src python3 tests/integration/verify_native_protocol.py \
  --launcher "$tmp/bin/claude-code-efficiency" --out "$tmp/check"
rm -rf "$tmp"
```

The native check exercises the installed launcher/helpers, permissions, validators, usage capture, and bounded commit reminders. Fake API usage is not performance evidence.

## Uninstall

Remove the installed package directory and launcher. Private state is retained unless you explicitly remove it. No user auth/settings need restoration.

## License and attribution

MIT (`LICENSE`). Action Fusion concepts reference NVIDIA's SoL-Pi, commit `1559b5cb12c72da4a485bc50fe326586b216fb19`; retain `NVIDIA-LICENSE.txt`. The native hook implementation does not rewrite Claude's arbitrary prompt/history or register new tool schemas.
