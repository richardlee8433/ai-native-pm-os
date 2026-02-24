# AI-Native PM OS v3.0 (Route A) Overview

Route A optimizes cost and speed by widening early and deepening only where needed:

- **L1 (Collect previews)**: ingest broad external signals and persist compact preview notes.
- **L2 (Weekly shortlist / PM entry)**: score and rank L1 signals into a weekly Top-K note for PM review.
- **L3 (Selective deepening)**: fetch full evidence only for Top-K candidates and append evidence into the same signal note.
- **L4 (Gate decision, immutable)**: PM makes judgment decisions and records immutable `GATE_DECISION` notes.
- **L5 (Writeback routing)**: publish to working layers automatically; route LTI/RTI to staging unless explicitly human-approved.

## PM intervention points

- PM starts at **L2** by reviewing `Weekly-Intel-YYYY-Wxx.md` shortlist outputs.
- PM final judgment is recorded at **L4** in immutable decision notes.
- LTI/RTI publication requires explicit human approval at L5.

## Route A operating principle

1. Collect a wide preview set in L1.
2. Score and shortlist in L2.
3. Fetch full evidence only for Top-K in L3.
4. Decide in L4.
5. Write back with routing guards in L5.

This keeps ingestion broad while concentrating expensive deep fetches and publication effort on high-value candidates.

## Storage layout (canonical)

- **L1 + L3**: `95_Signals/`
  - Signal note path: `95_Signals/SIG-*.md`
  - Frontmatter lifecycle: `status: raw | shortlisted | deepened | decided`
  - L3 full evidence is appended under `## Full Evidence (Fetched on ...)`
- **L2**: `96_Weekly_Review/`
  - Weekly note path: `96_Weekly_Review/Weekly-Intel-YYYY-Wxx.md`
- **L4**: `97_Decisions/`
  - Decision note path: `97_Decisions/DEC-YYYY-Wxx-NNN.md`
  - Immutable policy: never overwrite; create new revision files.
- **L5 writeback policy**
  - Auto-write default allowed only for working layers (`95/96/97`).
  - Human-gated final outputs:
    - `02_LTI/` (only if human approved)
    - `RTI/` (only if human approved)
  - AI staging folders:
    - `96_Weekly_Review/_LTI_Drafts/`
    - `97_Decisions/_RTI_Proposals/`
