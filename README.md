# Claude Code Efficiency Package

Small, stdlib-only helpers and supported native Claude Code hooks. No MCP server, model-backed reducer, credential changes or permission bypass. Requires Python 3.10+, Bash, Git and Claude Code on Linux.

**No guaranteed token or cost savings.** Fewer bytes or output tokens can still increase retries, cache traffic, latency or failures. Optimize cost per correctly completed task, not isolated payload size. Region handles are opt-in/advisory tools, not automatic context compression.

## What stays in the package

- **Action Fusion:** exact file changes and known validation in one permission-checked Bash call. Target locks span validation; interference is rejected. Failed validation retains edits and returns the real failure.
- **Strict patches and input repair:** no fuzzy matching. Inputs are archived before parsing. Repair changes archived input only; explicit reapplication is required.
- **Revision-bound region handles:** read exact lines, then send only replacement code. Any whole-file revision change invalidates the handle; no silent relocation.
- **Diagnostic compaction:** supported Ruff/Pyright JSON only, with omission receipts, original stream archives and exact recall. Unknown, malformed or nonbeneficial output falls back to the original. Checkers are never installed automatically.
- **Revision-aware read hints:** advisory, never suppressing user-requested reads or tests.
- **Optional completion guard:** bounded reminders for a required committed implementation and clean tree. Never auto-commits or certifies tests.
- **Optional local API accounting:** fresh/cache/write/output categories stay separate; missing accounting stays unknown. A separate Sonnet 5.5 price card supports hypothetical repricing, not actual billing.

Experimental documentation filtering, structured-workflow prompts, inactive history packing, benchmark runners and publication/analysis files are excluded. Historical evidence is archived separately, not shipped or committed here.

## Install and launch

```bash
python3 install.py
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

```bash
python3 ~/.local/share/claude-code-efficiency-package/operations.py \
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

Each hunk matches original content exactly once. No line numbers, fuzzy matching, deletes, renames or no-newline markers. Add File refuses existing targets. JSON `apply --spec -` supports exact replacements and multiple separate `then_run` entries. Files remain changed if validation fails; review the retained output rather than assuming success.

Large selective changes can use `region-read --file FILE --start N --end M`, then `region-replace region_ID --replacement - --then-run 'known check'`. Handles bind the entire original file hash. Lookup, receipts, retries and replacement code all count toward cost.

Inputs are content-addressed as `input_ID`. `repair-input ID --old 'unique bad fragment' --new 'replacement'` does not mutate source. Reapply the returned ID explicitly.

For structured checker output, use `--output-format ruff-json` with a standalone `ruff check . --output-format=json`, or `pyright-json` with `pyright --outputjson`. Never combine plain test output with structured JSON in one structured stream. Omitted details remain available through `check-recall CHECK_ID --stream stdout --offset 0 --limit 8192`.

## Runtime configuration

```bash
EFFICIENCY_CONFIG=/absolute/path/config.json claude-code-efficiency
python3 settings.py --config configs/native.json
```

Partial overrides are validated against `config.schema.json`; unknown/retired keys fail. Explicit environment overrides take precedence over JSON, then defaults. The launcher freezes a private resolved snapshot per session. Runtime keys:

- `profile`: `fused`, `native`, `before`.
- `regions.enabled`: enable revision-bound helper operations.
- `workflow.read_reuse_hints`: advisory hints for unchanged file revisions.
- `completion.require_commit`, `completion.max_reminders`: opt-in guard, 1–3 reminders.
- `checks.compact`, `checks.max_diagnostics`, `checks.max_bytes`.

Old experimental configs containing `documents`, `benchmark`, `objective` or `workflow.structured` are intentionally rejected. Create a runtime-only config rather than silently ignoring retired options. Permissions, original archives and failure preservation are not optimizer knobs.

The completion guard requires an explicit base commit:

```bash
EFFICIENCY_REQUIRE_COMMIT=1 EFFICIENCY_BASE_COMMIT="$(git rev-parse HEAD)" \
  claude-code-efficiency
```

Reminders are bounded; an unresolved violation remains unresolved after the limit. The guard does not establish semantic correctness.

## Accounting and hypothetical cost

`EFFICIENCY_ACCOUNTING=1` enables local raw API dumps for the direct Anthropic endpoint. They contain private conversation/source content; do not publish them. Exporters are disabled. Unsupported providers are not assigned invented billing rates. Missing final/in-flight usage remains unknown. Manual `EFFICIENCY_CACHE_TTL=5m|1h` is available; no priming or keepalives.

`simulated_cost.py` and `sonnet55-simulation.json` provide explicit hypothetical Sonnet 5.5 repricing: fresh $2/M, cache reads $0.20/M, output including thinking $10/M; writes $2.50/M (5m) or $4/M (1h). No batch/geography/tier modifiers. `objective(attempts)` includes failed-attempt spending, rejects incomplete accounting and requires the preregistered correctness floor (default 100%). Zero successes means undefined cost per correct task. Local tokenizers/cache reuse/trajectories are not calibrated Claude behavior; any assumed-zero writes must be requested explicitly and are labeled, never treated as measured billing.

## Verify

```bash
python3 -m unittest discover -v
bash -n launcher.sh
python3 build_config_schema.py
# Optional deterministic native integration test; fake API, no model generation:
python3 verify_native_protocol.py --out /tmp/claude-efficiency-native-check
```

Install first before the native check; it exercises the installed launcher/helpers, native permissions, validators, accounting and bounded commit reminders. Fake API usage is not performance evidence.

## Uninstall

Remove the installed package directory and launcher. Private state is retained unless you explicitly remove it. No user auth/settings need restoration.

## License and attribution

MIT (`LICENSE`). Action Fusion concepts reference NVIDIA's SoL-Pi, commit `1559b5cb12c72da4a485bc50fe326586b216fb19`; retain `NVIDIA-LICENSE.txt`. The native hook implementation does not rewrite Claude's arbitrary prompt/history or register new tool schemas.
