# Decision BG-1: NVIDIA Nemotron qualification (background log synthesis)

- Date: 2026-11-23 · Author: Architect / BOT-CEO (Claude Opus 5.5) · requested by the user
- Model: `nvidia-nemotron/nvidia/nemotron-3-ultra-550b-a55b` via `opencode run`, agent
  `background` (edit deny, bash deny, webfetch deny, task deny), run in a scratch snapshot
  outside the repo. Input: 15 public `.agents/` files from `main` 12181ef + CEO notes,
  SHA-256 snapshot. No real watershed data (`logs/run.log` deliberately not sent).
- Pricing / quota of the NVIDIA endpoint: **not verified**; one task, user-approved.

## Result

- Elapsed 161 s (deadline 15 min), exit 0, 32 findings, 20 proposals; snapshot hashes
  unchanged and no file created afterwards.
- Expected answers written before dispatch: **5/5 found** (E1 trace race #10, E2 finite
  penalty #1, E3 `agm` done-recipient #22, E4 committed-only reviewer #23/#26, E5 skipped
  gates #29). No invented test runs or numbers found on spot-check.

## Verdict: PASS with two conditions

1. **Permission gap (harness, Major):** the agent used OpenCode's `execute` tool (JavaScript,
   `fs.readFileSync`) although `bash` was denied. It only read, but `execute` could write.
   Every read-only OpenCode agent (`background`, `explore`, `reviewer`, `auditor`) must deny
   `execute` explicitly; `edit: deny` + `bash: deny` is not a read-only boundary.
2. **Stale findings:** it reported findings already fixed (e.g. #2-#9, #19, #30 — fixed in
   REV-1 / ARCH-1, merged) as if open. Briefs must ask for a `status: open | resolved | unknown`
   per finding, with the evidence for "resolved".

Role `background-nemotron` is qualified for log synthesis under these conditions. Kimi and
Mistral remain unqualified. Output is input for the harness retro, not a merge gate.
