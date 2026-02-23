from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable

from orchestrator.storage import JSONLStorage

L5_DATA_DIRNAME = "test_data"
LTI_DRAFTS_JSONL = "lti_drafts.jsonl"
RTI_PROPOSALS_JSONL = "rti_proposals.jsonl"
LTI_INDEX_JSON = "lti_index.json"
RTI_INDEX_JSON = "rti_index.json"

LTI_DRAFTS_DIR = Path("96_Weekly_Review") / "_LTI_Drafts"
RTI_PROPOSALS_DIR = Path("97_Decisions") / "_RTI_Proposals"
RTI_FINAL_DIR = Path("RTI")
LTI_FINAL_DIR = Path("02_LTI")

DECISION_DIRS = [Path("97_Decisions"), Path("97_Gate_Decisions")]


@dataclass(frozen=True)
class L4Decision:
    decision_id: str
    decision_type: str
    signal_id: str | None
    revision_of: str | None


def route_after_gate_decision(decision_id: str, data_dir: Path, vault_dir: Path) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    decision_path = _resolve_decision_path(decision_id, vault_dir)
    if decision_path is None:
        return [{"error": f"decision not found: {decision_id}"}]

    decision = _parse_decision(decision_path)
    if decision.decision_type == "ACCEPT":
        if not decision.signal_id:
            _log_error(f"[L5] missing signal_id in decision {decision.decision_id}")
            return [{"error": "missing signal_id"}]
        draft = _ensure_lti_draft(decision, data_dir, vault_dir)
        if draft:
            created.append({"type": "lti_draft", "id": draft["id"], "path": draft["vault_path"]})
        _mark_signal_decided(decision.signal_id, draft["id"] if draft else None, data_dir)
    elif decision.decision_type in {"REJECT", "DEFER"}:
        return []
    return created


def check_rule_of_three_and_propose_rti(pattern_id: str, data_dir: Path, vault_dir: Path) -> str | None:
    cos_index_path = data_dir / "cos_index.json"
    if not cos_index_path.exists():
        return None
    cos_index = json.loads(cos_index_path.read_text(encoding="utf-8"))
    matches = [entry for entry in cos_index if entry.get("pattern_key") == pattern_id]
    if len(matches) < 3:
        return None

    proposals_store = _rti_store(data_dir)
    existing = _find_recent_rti_proposal(pattern_id, proposals_store.read_all())
    if existing:
        return existing["id"]

    proposal = _create_rti_proposal(pattern_id, matches, data_dir, vault_dir)
    return proposal["id"]


def publish_lti_draft(draft_id: str, vault_dir: Path, data_dir: Path, reviewer: str, review_notes: str) -> str:
    drafts_store = _lti_store(data_dir)
    drafts = drafts_store.read_all()
    draft = _find_by_id(drafts, draft_id)
    if not draft:
        raise ValueError(f"Draft not found: {draft_id}")
    if draft["status"] == "published":
        return draft["final_vault_path"]

    source = vault_dir / draft["vault_path"]
    final_name = _final_lti_name(draft_id)
    target = vault_dir / LTI_FINAL_DIR / final_name
    _move_with_frontmatter_update(
        source=source,
        target=target,
        updates={
            "status": "published",
            "published_at": _utc_now(),
            "reviewer": reviewer,
            "review_notes": review_notes,
        },
    )

    draft["status"] = "published"
    draft["published_at"] = _utc_now()
    draft["updated_at"] = _utc_now()
    draft["final_vault_path"] = str(target.relative_to(vault_dir).as_posix())
    draft.setdefault("governance", {})
    draft["governance"]["reviewer"] = reviewer
    draft["governance"]["review_notes"] = review_notes
    drafts_store.rewrite_all(drafts)

    _write_index(LTI_INDEX_JSON, drafts, data_dir, ["id", "status", "created_at", "vault_path", "source_signal_id", "source_decision_id"])
    return draft["final_vault_path"]


def reject_lti_draft(draft_id: str, data_dir: Path, vault_dir: Path, reviewer: str, reason: str) -> None:
    drafts_store = _lti_store(data_dir)
    drafts = drafts_store.read_all()
    draft = _find_by_id(drafts, draft_id)
    if not draft:
        raise ValueError(f"Draft not found: {draft_id}")
    if draft["status"] == "rejected":
        return
    draft["status"] = "rejected"
    draft["rejected_at"] = _utc_now()
    draft["updated_at"] = _utc_now()
    draft.setdefault("governance", {})
    draft["governance"]["reviewer"] = reviewer
    draft["governance"]["review_notes"] = reason

    draft_path = vault_dir / draft["vault_path"]
    _update_frontmatter(
        draft_path,
        {
            "status": "rejected",
            "rejected_at": _utc_now(),
            "reviewer": reviewer,
            "review_notes": reason,
        },
    )
    drafts_store.rewrite_all(drafts)
    _write_index(LTI_INDEX_JSON, drafts, data_dir, ["id", "status", "created_at", "vault_path", "source_signal_id", "source_decision_id"])


def publish_rti_proposal(proposal_id: str, vault_dir: Path, data_dir: Path, reviewer: str, review_notes: str) -> str:
    store = _rti_store(data_dir)
    proposals = store.read_all()
    proposal = _find_by_id(proposals, proposal_id)
    if not proposal:
        raise ValueError(f"Proposal not found: {proposal_id}")
    if proposal["status"] == "published":
        return proposal["final_vault_path"]

    source = vault_dir / proposal["vault_path"]
    target = vault_dir / RTI_FINAL_DIR / _final_rti_name(proposal_id)
    _move_with_frontmatter_update(
        source=source,
        target=target,
        updates={
            "status": "published",
            "published_at": _utc_now(),
            "reviewer": reviewer,
            "review_notes": review_notes,
        },
    )

    proposal["status"] = "published"
    proposal["published_at"] = _utc_now()
    proposal["updated_at"] = _utc_now()
    proposal["final_vault_path"] = str(target.relative_to(vault_dir).as_posix())
    proposal["reviewer"] = reviewer
    proposal["review_notes"] = review_notes
    store.rewrite_all(proposals)
    _write_index(RTI_INDEX_JSON, proposals, data_dir, ["id", "status", "created_at", "vault_path", "pattern_id"])
    return proposal["final_vault_path"]


def reject_rti_proposal(proposal_id: str, data_dir: Path, vault_dir: Path, reviewer: str, reason: str) -> None:
    store = _rti_store(data_dir)
    proposals = store.read_all()
    proposal = _find_by_id(proposals, proposal_id)
    if not proposal:
        raise ValueError(f"Proposal not found: {proposal_id}")
    if proposal["status"] == "rejected":
        return
    proposal["status"] = "rejected"
    proposal["rejected_at"] = _utc_now()
    proposal["updated_at"] = _utc_now()
    proposal["reviewer"] = reviewer
    proposal["review_notes"] = reason

    proposal_path = vault_dir / proposal["vault_path"]
    _update_frontmatter(
        proposal_path,
        {
            "status": "rejected",
            "rejected_at": _utc_now(),
            "reviewer": reviewer,
            "review_notes": reason,
        },
    )
    store.rewrite_all(proposals)
    _write_index(RTI_INDEX_JSON, proposals, data_dir, ["id", "status", "created_at", "vault_path", "pattern_id"])


def list_staged(data_dir: Path, *, artifact_type: str, status: str | None = None) -> list[dict[str, Any]]:
    if artifact_type == "lti":
        rows = _lti_store(data_dir).read_all()
    elif artifact_type == "rti":
        rows = _rti_store(data_dir).read_all()
    else:
        raise ValueError(f"Unknown type: {artifact_type}")
    if status:
        return [row for row in rows if row.get("status") == status]
    return rows


def _ensure_lti_draft(decision: L4Decision, data_dir: Path, vault_dir: Path) -> dict[str, Any] | None:
    drafts_store = _lti_store(data_dir)
    drafts = drafts_store.read_all()
    existing = next((row for row in drafts if row.get("source_decision_id") == decision.decision_id), None)
    if existing:
        return existing

    signals_path = data_dir / "signals.jsonl"
    signal_payload = _find_signal(signals_path, decision.signal_id)
    now = _utc_now()
    draft_id, draft_path = _reserve_unique_path("LTI-DRAFT", now, drafts, vault_dir / LTI_DRAFTS_DIR)
    title = signal_payload.get("title") if signal_payload else f"LTI Draft {draft_id}"
    summary = (signal_payload.get("content") if signal_payload else "") or f"Draft created from decision {decision.decision_id}."

    evidence_refs = _build_evidence_refs(signal_payload)
    _write_atomic(draft_path, _render_lti_draft_markdown(draft_id, decision, title, summary, now))

    record = {
        "id": draft_id,
        "type": "lti_draft",
        "source_signal_id": decision.signal_id,
        "source_decision_id": decision.decision_id,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "vault_path": str(draft_path.relative_to(vault_dir).as_posix()),
        "final_vault_path": None,
        "title": title or "",
        "summary": summary or "",
        "tags": signal_payload.get("impact_area") if signal_payload else [],
        "evidence_refs": evidence_refs,
        "governance": {"reviewer": None, "review_notes": None},
    }
    drafts.append(record)
    drafts_store.rewrite_all(drafts)
    _write_index(LTI_INDEX_JSON, drafts, data_dir, ["id", "status", "created_at", "vault_path", "source_signal_id", "source_decision_id"])
    return record


def _create_rti_proposal(pattern_id: str, matches: list[dict[str, Any]], data_dir: Path, vault_dir: Path) -> dict[str, Any]:
    store = _rti_store(data_dir)
    proposals = store.read_all()
    now = _utc_now()
    proposal_id, proposal_path = _reserve_unique_path("RTI-PROP", now, proposals, vault_dir / RTI_PROPOSALS_DIR)
    supporting_ids = [entry.get("cos_id") for entry in matches if entry.get("cos_id")]

    _write_atomic(
        proposal_path,
        _render_rti_proposal_markdown(proposal_id, pattern_id, supporting_ids, now),
    )

    record = {
        "id": proposal_id,
        "type": "rti_proposal",
        "status": "draft",
        "pattern_id": pattern_id,
        "supporting_cos_case_ids": supporting_ids,
        "created_at": now,
        "updated_at": now,
        "published_at": None,
        "rejected_at": None,
        "vault_path": str(proposal_path.relative_to(vault_dir).as_posix()),
        "final_vault_path": None,
        "hypothesis_update": "Pending review.",
        "proposed_change": "Pending review.",
        "rollback_plan": "Pending review.",
        "reviewer": None,
        "review_notes": None,
    }
    proposals.append(record)
    store.rewrite_all(proposals)
    _write_index(RTI_INDEX_JSON, proposals, data_dir, ["id", "status", "created_at", "vault_path", "pattern_id"])
    return record


def _find_recent_rti_proposal(pattern_id: str, proposals: list[dict[str, Any]]) -> dict[str, Any] | None:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=90)
    for proposal in proposals:
        if proposal.get("pattern_id") != pattern_id:
            continue
        if proposal.get("status") not in {"draft", "published"}:
            continue
        created_at = _parse_datetime(proposal.get("created_at"))
        if created_at and created_at >= cutoff:
            return proposal
    return None


def _mark_signal_decided(signal_id: str, lti_draft_id: str | None, data_dir: Path) -> None:
    if not signal_id:
        return
    signals_path = data_dir / "signals.jsonl"
    if not signals_path.exists():
        return
    rows = JSONLStorage(signals_path).read_all()
    updated = False
    for row in rows:
        if row.get("id") == signal_id:
            row["lifecycle_status"] = "decided"
            if lti_draft_id:
                row["lti_draft_id"] = lti_draft_id
            updated = True
            break
    if updated:
        JSONLStorage(signals_path).rewrite_all(rows)


def _resolve_decision_path(decision_id: str, vault_dir: Path) -> Path | None:
    for decision_dir in DECISION_DIRS:
        candidate = vault_dir / decision_dir / f"{decision_id}.md"
        if candidate.exists():
            return candidate
    return None


def _parse_decision(decision_path: Path) -> L4Decision:
    frontmatter = _read_frontmatter(decision_path)
    decision_type = (frontmatter.get("decision_type") or frontmatter.get("decision") or "").strip()
    if decision_type.lower() in {"approved", "approve"}:
        decision_type = "ACCEPT"
    elif decision_type.lower() in {"reject", "rejected"}:
        decision_type = "REJECT"
    elif decision_type.lower() in {"deferred", "needs_more_info", "defer", "hold"}:
        decision_type = "DEFER"
    decision_id = decision_path.stem
    return L4Decision(
        decision_id=decision_id,
        decision_type=decision_type.upper(),
        signal_id=(frontmatter.get("signal_id") or "").strip() or None,
        revision_of=(frontmatter.get("revision_of") or "").strip() or None,
    )


def _read_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _render_lti_draft_markdown(draft_id: str, decision: L4Decision, title: str | None, summary: str | None, now: str) -> str:
    return "\n".join(
        [
            "---",
            f"id: {draft_id}",
            "type: lti_draft",
            "status: draft",
            f"created_at: {now}",
            f"source_signal_id: {decision.signal_id or ''}",
            f"source_decision_id: {decision.decision_id}",
            "review_required: true",
            "tags: []",
            "---",
            "",
            f"# {title or draft_id}",
            "",
            "## Why it matters (Outcome framing)",
            summary or "",
            "",
            "## Evidence",
            "-",
            "",
            "## Decision Trace",
            f"- decision_id: {decision.decision_id}",
            "",
            "## Draft to Publish Checklist (human)",
            "- [ ] Evidence verified",
            "- [ ] Claims checked",
            "- [ ] OK to publish",
            "",
            "## Notes",
            "",
        ]
    )


def _render_rti_proposal_markdown(proposal_id: str, pattern_id: str, supporting_ids: Iterable[str], now: str) -> str:
    support_lines = "\n".join(f"- {item}" for item in supporting_ids) or "- None"
    return "\n".join(
        [
            "---",
            f"id: {proposal_id}",
            "type: rti_proposal",
            "status: draft",
            f"pattern_id: {pattern_id}",
            f"created_at: {now}",
            "review_required: true",
            "---",
            "",
            "# Proposed RTI Revision",
            "",
            "## Pattern Evidence (COS cases)",
            support_lines,
            "",
            "## Proposed Theory Change",
            "",
            "## Risks / Tradeoffs",
            "",
            "## Rollback Plan",
            "",
            "## Review Checklist",
            "- [ ] Evidence reviewed",
            "- [ ] Risks assessed",
            "- [ ] Ready to publish",
            "",
        ]
    )


def _lti_store(data_dir: Path) -> JSONLStorage:
    return JSONLStorage(_data_root(data_dir) / LTI_DRAFTS_JSONL)


def _rti_store(data_dir: Path) -> JSONLStorage:
    return JSONLStorage(_data_root(data_dir) / RTI_PROPOSALS_JSONL)


def _data_root(data_dir: Path) -> Path:
    root = data_dir / L5_DATA_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_index(index_name: str, rows: list[dict[str, Any]], data_dir: Path, fields: list[str]) -> None:
    payload = [
        {key: row.get(key) for key in fields}
        for row in rows
    ]
    path = _data_root(data_dir) / index_name
    _write_atomic(path, json.dumps(payload, indent=2))


def _find_signal(signals_path: Path, signal_id: str | None) -> dict[str, Any]:
    if not signal_id or not signals_path.exists():
        return {}
    return next((row for row in JSONLStorage(signals_path).read_all() if row.get("id") == signal_id), {})


def _build_evidence_refs(signal: dict[str, Any]) -> list[dict[str, str]]:
    url = signal.get("url")
    if not url:
        return []
    kind = "arxiv" if "arxiv.org" in url else "url"
    return [{"kind": kind, "ref": url}]


def _next_id(prefix: str, now_iso: str, rows: list[dict[str, Any]], *, offset: int = 0) -> str:
    date_key = now_iso.split("T")[0].replace("-", "")
    matching = [row for row in rows if str(row.get("id", "")).startswith(f"{prefix}-{date_key}-")]
    return f"{prefix}-{date_key}-{len(matching) + 1 + offset:03d}"


def _reserve_unique_path(prefix: str, now_iso: str, rows: list[dict[str, Any]], base_dir: Path) -> tuple[str, Path]:
    for offset in range(2):
        candidate_id = _next_id(prefix, now_iso, rows, offset=offset)
        candidate_path = base_dir / f"{candidate_id}.md"
        if not candidate_path.exists():
            return candidate_id, candidate_path
    raise FileExistsError(f"{prefix} path collision after retry in {base_dir}")


def _find_by_id(rows: list[dict[str, Any]], target_id: str) -> dict[str, Any] | None:
    return next((row for row in rows if row.get("id") == target_id), None)


def _final_lti_name(draft_id: str) -> str:
    suffix = draft_id.replace("LTI-DRAFT-", "")
    return f"LTI-{suffix}.md"


def _final_rti_name(proposal_id: str) -> str:
    suffix = proposal_id.replace("RTI-PROP-", "")
    return f"RTI-{suffix}.md"


def _move_with_frontmatter_update(*, source: Path, target: Path, updates: dict[str, str]) -> None:
    content = source.read_text(encoding="utf-8")
    updated = _apply_frontmatter_updates(content, updates)
    _write_atomic(target, updated)
    source.unlink(missing_ok=True)


def _update_frontmatter(path: Path, updates: dict[str, str]) -> None:
    content = path.read_text(encoding="utf-8")
    updated = _apply_frontmatter_updates(content, updates)
    _write_atomic(path, updated)


def _apply_frontmatter_updates(content: str, updates: dict[str, str]) -> str:
    if not content.startswith("---\n"):
        frontmatter = "\n".join([f"{key}: {value}" for key, value in updates.items()])
        return f"---\n{frontmatter}\n---\n\n{content}"
    end_idx = content.find("\n---\n", 4)
    if end_idx == -1:
        return content
    frontmatter = content[4:end_idx]
    body = content[end_idx + 5 :]
    for key, value in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", flags=re.MULTILINE)
        line = f"{key}: {value}"
        if pattern.search(frontmatter):
            frontmatter = pattern.sub(line, frontmatter)
        else:
            frontmatter += f"\n{line}"
    return f"---\n{frontmatter}\n---\n{body}"


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _log_error(message: str) -> None:
    print(message)
