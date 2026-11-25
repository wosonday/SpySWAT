# HARN-3 — sync the harness copy with the shared harness (2026-11-25 retro)

- tier: none (single Claude session plays every role; docs only)
- scope: `AGENTS-TUTORIAL.md`, `docs/AGY-GEMINI-OPUS.md`, `docs/CLAUDE-ARCHITECT-CEO.md`, `docs/COPILOT-GIT.md`,
  `docs/NVIDIA-BACKGROUND.md`, `docs/OPENCODE-WORKERS-REVIEWER.md`, `docs/README.md`, `docs/WINDOWS-AGENT-RUNTIME.md`,
  plus this task file and `.agents/log/HARN-3.md`.
- goal: copy the 2026-11-25 retro from the shared harness byte for byte (agy-first reviewer routing, prompt files for
  `agy`, Hydrogen fallback editor, Neon pre-review, worker-completion tracking, merge trials, dirty-checkout exception,
  cleanup briefs, Mistral log summaries).
- acceptance: harness lint 0 errors; the 97 harness tests pass; no project-specific text in the copied files.
