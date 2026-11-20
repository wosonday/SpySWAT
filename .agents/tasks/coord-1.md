---
id: coord-1
branch: fix/phase1-correctness
tier: strong
skills: diagnosing-bugs, opencode
gitnexus: none
---

# coord-1: verify open issues, consult agy, hand off to Opus

## Request
The user requested inspection of the current problems, discussion with agy, and
an evidence-based report to reviewer Opus.

## Scope
- Inspect the existing REV-1, ARCH-1 and DOCS-3 work without overwriting it.
- Run synthetic tests and process-local diagnostic experiments.
- Write `.agents/log/coord-1.md` and `.agents/reports/coord-1.md`.
- Consult agy read-only and send the report to the existing SpySWAT Opus session.
- Reviewer owns `.agents/reviews/coord-1-1.md` for the requested read-only review;
  no source edits, commits or merges are requested from that session.

## Constraints
- REV-1 reserves finding 1's implementation/design choice to the user.
- ARCH-1 remains proposed; do not perform the structural refactor.
- Do not modify product code, tests, agent permissions or other agents' notebooks.
- Do not stage or commit the pre-existing mixed worktree changes.
- No merge, release, real watershed data or confidential input files.
- A diagnostic monkeypatch is not a source fix or a passing release gate.

## Acceptance
- Record current unpatched test counts and the exact failing cases.
- Separate confirmed problems, diagnostic evidence and unapproved proposals.
- Record agy's actual response, including any unavailable or failed consultation.
- Send a short report pointer to the verified SpySWAT Opus session.
- Mark dirty-worktree and remaining approval blockers explicitly.
