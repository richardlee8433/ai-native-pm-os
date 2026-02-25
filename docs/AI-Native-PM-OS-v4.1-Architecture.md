# AI-Native PM OS v4.1: Human-Augmented Validation Architecture

**Version:** 4.1  
**Date:** 2026-02-25  
**Status:** Current Architecture  
**Upgrade From:** v4.0 Reality-Validated OS

---

## Executive Summary

v4.1 preserves the v4.0 five-layer operating system while adding **human-augmented validation** so early-stage knowledge can progress without waiting for full metrics. The system remains reality-validated: **no promotion without an AVL Evidence Pack**, and governance updates remain conservative.

**Operating Formula:**

```
Graph -> AVL (Manual or Automated) -> LTI (Provisional/Validated) -> RTI Review (if governance impact) -> Execution -> Writeback
```

---

## 1. Five-Layer Operating System (v4.0 Baseline)

1. **Layer I: Graph** (exploration)
2. **Layer II: Applied Validation (AVL)** (reality testing)
3. **Layer III: LTI** (distillation & publication)
4. **Layer IV: RTI** (governance kernel)
5. **Layer V: Execution & Writeback**

---

## 2. Human-Augmented Validation (v4.1 Upgrade)

### 2.1 AVL Validation Modes

**Mode A — Manual Project-Cycle Validation (early default)**
- Used for new concepts or low-sample domains.
- Requires structured human validation and an Evidence Pack.

**Mode B — Decision Replay Validation (CX Universe)**
- Replays canonical cases to test decision rules.
- Produces structured evidence and delta vs. baseline.

**Mode C — Automated Metrics Validation (mature stage)**
- Retains v4.0 metric gates (test_count, success_rate, variance, cost).

### 2.2 Evidence Pack as Formal Requirement

Every promotion requires an AVL Evidence Pack with:
- Hypothesis
- Context
- Method (project_cycle | replay)
- Outcome (pass/strong_partial/partial/fail)
- Cost Paid
- Failure Modes
- Delta
- Recommendation (promote/revise/archive)
- Governance Impact (none/review/triggers)

No Evidence Pack -> no promotion.

---

## 3. Promotion Router v4.1 (Additive)

### Step 1 — LTI Promotion
Allow promotion when:
- Evidence Pack is complete
- Outcome = pass or strong_partial
- Recommendation = promote
- Failure modes documented
- Maintainer approval captured

Mark resulting LTI as **provisional** or **validated_metrics**.

### Step 2 — RTI Review Trigger
Only if governance impact is **review** or **triggers**:
- Create RTI review proposal
- Do not directly update RTI

---

## 4. Provisional LTI Revalidation

Provisional LTIs must be revalidated within 28 days.
- Track `revalidate_by` and `revalidate_status`
- Maintain a revalidation queue and reminders

---

## 5. Backward Compatibility

- v3.0 flow remains default and unchanged.
- v4.1 behavior is additive and opt-in.
- Old architecture files are preserved for reference.
