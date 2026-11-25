# DOCS-6 — refresh README test counts and notebook pointers

- tier: none (single Claude session plays every role; docs only)
- scope: `README.md`, `README_VI.md`, `.agents/README.md`, `AGENTS.md` (Commands section only), this task file,
  `.agents/log/DOCS-6.md`.
- goal: replace the stale `464 passed, 11 skipped` counts with the measured result on main, list the new POSIX-only
  skip file, add the missing English `## Tests` section (mirrors README_VI), and point `.agents/README.md` to the
  current sections of `AGENTS-TUTORIAL.md`.
- acceptance: numbers match a real `pytest tests/ -q` run on main; harness lint 0 errors; harness tests pass.
