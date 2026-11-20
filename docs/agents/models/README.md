# Model-Specific Usage Guides

This directory specifies startup commands, permission boundaries, `agm`/`hc` usage, and quota-saving practices for each model/CLI in [AGENTS-TUTORIAL.md](../AGENTS-TUTORIAL.md), [BOT-CEO.md](../BOT-CEO.md), and [HERDR-CORE-BOT.md](../HERDR-CORE-BOT.md).

## Index

| Document | Model / Tool | Primary Role |
|---|---|---|
| [CLAUDE-ARCHITECT-CEO.md](CLAUDE-ARCHITECT-CEO.md) | Claude Code (`claude-opus-5-5`, `claude-fable-5-2`) | Architect / BOT-CEO, lane budget allocation, high-risk escalations |
| [CODEX-ENGINEERING.md](CODEX-ENGINEERING.md) | Codex CLI / `openai/gpt-6.1-sol` | Hard engineering, fixes after 2 failed attempts, complex cross-reviews, single-lane management |
| [AGY-GEMINI-OPUS.md](AGY-GEMINI-OPUS.md) | Antigravity CLI `agy` (3.8 Flash, Hydrogen Low/Medium, Argon, Opus High) | Fast research (`3.8-flash-low`), lightweight docs/reports (`3.8-flash-medium` / `hydrogen-low`), technical advisor & harness optimization (`argon`), Co-Architect & Senior Reviewer (`Opus High`) |
| [OPENCODE-WORKERS-REVIEWER.md](OPENCODE-WORKERS-REVIEWER.md) | DeepSeek Flash/Pro on OpenCode Go; scripts/CI and approved fallbacks | Flash for fast/mid/explore; Pro for qualified review/strong work |
| [NVIDIA-BACKGROUND.md](NVIDIA-BACKGROUND.md) | NVIDIA Kimi, Mistral, Nemotron | Read-only background synthesis/proposals/logs; not a merge gate, not benchmarked |
| [HARNESS-LINT.md](HARNESS-LINT.md) | Python 3.11+, standard library only | Links/anchors, Markdown structure, model IDs, bilingual routing and safety contracts |
| [COPILOT-GIT.md](COPILOT-GIT.md) | GitHub Copilot CLI (`copilot`) | Git version manager: reads `BRANCHES.md`, merges exact SHA, post-merge verification, reverts, cleans up worktrees/branches |
| [ESLINT-CI-GUARDRAILS.md](ESLINT-CI-GUARDRAILS.md) | ESLint (`--max-warnings 0`) + Git Diff Check + GitHub Actions CI | **Mandatory guardrails for all models:** blocks `any`, `@ts-ignore`, `eslint-disable`, bloated functions, missing `await`; enforced at Audit/CI so lightweight models can be used safely |

## Quick Quota Check Before Dispatch

Claude CEO follows the [shared budget policy](../AGENTS-TUTORIAL.md#311-điều-phối-kinh-phí-ai). Check Go's **5-hour, weekly and monthly** allowances in the [Go Console](https://opencode.ai/console/go), not from `agm` token counts. For other quotas and usage by tool:

```powershell
agm quota                     # check 5h / 7d quota % for Claude and Codex
agm cost --by source          # check token share across claude / codex / opencode / agy
```

| Situation | Load-balancing action |
|---|---|
| Go near its limit, exhausted or unverified | Near its limit: reserve capacity for review/rework and priorities. Exhausted/unverified: use a capable approved source or mark blocked; never enable Extra Usage autonomously |
| `codex` 7d > 70–80% | Reserve `openai/gpt-6.1-sol` for genuinely hard engineering; routine review still uses Go first or a preapproved `agy` fallback |
| `claude` 5h/7d rising fast | Open an interactive `agy` Opus High session inside the repo (`--mode plan --sandbox`, keeping `conversation_id` for prompt cache) to offload design/task splitting and hard-case review; never open Claude for routine reviews |
| `:free` endpoint hits `429` | Switch to a fallback `:free` slug or local Ollama (`num_ctx ≥ 64k`) |
| NVIDIA `429`, timeout or late output | Do not rotate aliases to bypass quota or layer retries; the CEO checks the previous task/deadline and SHA/snapshot before use |

Confirmed IDs: `opencode-go/deepseek-v4.1-flash`, `opencode-go/deepseek-v4-pro`. Go is enabled but still requires Console checks and role qualification; DeepSeek is not assumed free and Personal/API `opencode/deepseek-*` is not a silent substitute. NVIDIA does not replace Review/Audit/Docs/Argon.

## Verify Documents Before Handoff

```powershell
python -B scripts/lint_harness.py
python -B -m unittest discover -s tests -v
```

Run from the `agent-tutorial` root, without Git, networking or API keys. See [lint coverage and limitations](HARNESS-LINT.md).

> **SpySWAT:** the harness lint scripts are not vendored in this repository (they expect the
> `agent-tutorial` layout and its JS/TS guardrail examples). Run them in the `agent-tutorial`
> repository. The SpySWAT gate is `pytest tests/ -q` + `git diff --check`; the
> ESLint guide applies to JS/TS projects only — its principle (zero-warning checks at Audit/CI,
> no bypass comments) carries over to Python tests here.
