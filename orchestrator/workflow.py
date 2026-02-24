from __future__ import annotations

import datetime as dt
import json
import os
import hashlib
import re
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from pm_os_contracts.models import ACTION_TASK, LTI_NODE, RTI_NODE, SIGNAL

from orchestrator.storage import JSONLStorage
from orchestrator.vault_ops import _excerpt, write_gate_decision, write_lti_markdown, write_rti_markdown, write_signal_markdown
from orchestrator.l5_routing_guard import route_after_gate_decision, check_rule_of_three_and_propose_rti

DEFAULT_NEXT_ACTIONS = {
    "approved": ["Deepen evidence (L3 full fetch)", "Draft LTI insight note"],
    "needs_more_info": ["Fetch full article body", "Re-evaluate after deepening"],
    "deferred": ["Re-evaluate in next weekly cycle"],
    "reject": ["Archive signal"],
}


class Orchestrator:
    def __init__(
        self,
        data_dir: Path,
        *,
        now_provider: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.now_provider = now_provider or (lambda: dt.datetime.now(tz=dt.timezone.utc))

        vault_root = os.getenv("PM_OS_VAULT_ROOT", ".vault_test")
        self.vault_root = Path(vault_root)

        self.signals = JSONLStorage(self.data_dir / "signals.jsonl")
        self.tasks = JSONLStorage(self.data_dir / "weekly_tasks.jsonl")
        self.writebacks = JSONLStorage(self.data_dir / "writebacks.jsonl")
        self.lti_nodes = JSONLStorage(self.data_dir / "lti_nodes.jsonl")
        self.rti_nodes = JSONLStorage(self.data_dir / "rti_nodes.jsonl")
        self.decision_index_path = self.data_dir / "decision_index.json"
        self.cos_index_path = self.data_dir / "cos_index.json"

    def run_deepening(
        self,
        *,
        limit: int = 5,
        only_pending: bool = True,
        force: bool = False,
        signal_id: str | None = None,
        vault_root: str | None = None,
    ) -> dict[str, Any]:
        resolved_vault_root = Path(vault_root) if vault_root else self.vault_root
        now = self.now_provider().replace(microsecond=0)
        now_iso = now.isoformat()

        tasks = self.tasks.read_all()
        signals = self.signals.read_all()
        signals_by_id = {row.get("id"): row for row in signals if isinstance(row.get("id"), str)}

        report = {"processed": 0, "completed": 0, "failed": 0, "skipped": 0, "results": []}
        matched = 0

        for task in tasks:
            if task.get("type") != "deepening":
                continue
            task_signal_id = task.get("signal_id")
            if signal_id and task_signal_id != signal_id:
                continue
            if not isinstance(task_signal_id, str):
                report["skipped"] += 1
                report["results"].append({"signal_id": None, "task_id": task.get("id"), "status": "skipped", "reason": "missing signal_id"})
                continue

            status = task.get("status")
            if only_pending and not force and status != "pending":
                report["skipped"] += 1
                report["results"].append({"signal_id": task_signal_id, "task_id": task.get("id"), "status": "skipped", "reason": f"status={status}"})
                continue
            if not force and status == "completed":
                report["skipped"] += 1
                report["results"].append({"signal_id": task_signal_id, "task_id": task.get("id"), "status": "skipped", "reason": "already completed"})
                continue
            if matched >= limit:
                break
            matched += 1
            report["processed"] += 1

            signal_row = signals_by_id.get(task_signal_id)
            if signal_row is None:
                task["status"] = "failed"
                task["error"] = f"Signal not found: {task_signal_id}"
                task["completed_at"] = now_iso
                report["failed"] += 1
                report["results"].append({"signal_id": task_signal_id, "task_id": task.get("id"), "status": "failed", "error": task["error"]})
                continue

            evidence = self._fetch_evidence(signal_row)
            sig_path = resolved_vault_root / "95_Signals" / f"{task_signal_id}.md"
            if not sig_path.exists():
                write_signal_markdown(resolved_vault_root, signal_row)

            updated = self._append_deepened_evidence(
                sig_path=sig_path,
                source_url=signal_row.get("url"),
                task_id=task.get("id"),
                captured_at=now_iso,
                fetch_status=evidence["fetch_status"],
                excerpt=evidence["evidence_excerpt"],
            )

            if evidence["fetch_status"] == "ok":
                task["status"] = "completed"
                task["completed_at"] = now_iso
                task.pop("error", None)
                signal_row["deepened"] = True
                signal_row["deepened_at"] = now_iso
                signal_row["evidence_source_url"] = signal_row.get("url")
                signal_row["evidence_hash"] = evidence["evidence_hash"]
                report["completed"] += 1
                row_status = "completed"
            else:
                task["status"] = "failed"
                task["completed_at"] = now_iso
                task["error"] = evidence.get("error") or "fetch failed"
                signal_row["deepened"] = False
                report["failed"] += 1
                row_status = "failed"

            report["results"].append(
                {
                    "signal_id": task_signal_id,
                    "task_id": task.get("id"),
                    "status": row_status if updated else "skipped",
                    "sig_path": str(sig_path),
                }
            )

        self.tasks.rewrite_all(tasks)
        self.signals.rewrite_all(signals)
        return report

    def _fetch_evidence(self, signal_row: dict[str, Any]) -> dict[str, str]:
        url = signal_row.get("url")
        fallback = _excerpt(signal_row.get("content"), limit=2500)
        if not isinstance(url, str) or not url:
            return {
                "fetch_status": "failed",
                "error": "missing source url",
                "evidence_excerpt": fallback,
                "evidence_hash": hashlib.sha1(fallback.encode("utf-8")).hexdigest(),
            }

        try:
            if "arxiv.org" in url:
                excerpt = self._fetch_arxiv_evidence(url) or fallback
            else:
                excerpt = self._fetch_html_evidence(url)
            if not excerpt:
                excerpt = fallback
            excerpt = " ".join(excerpt.split())[:3000]
            return {
                "fetch_status": "ok",
                "evidence_excerpt": excerpt,
                "evidence_hash": hashlib.sha1(excerpt.encode("utf-8")).hexdigest(),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "fetch_status": "failed",
                "error": str(exc),
                "evidence_excerpt": fallback,
                "evidence_hash": hashlib.sha1(fallback.encode("utf-8")).hexdigest(),
            }

    def _fetch_html_evidence(self, url: str) -> str:
        response = self._http_get(url)
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", response, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return text

    def _fetch_arxiv_evidence(self, url: str) -> str:
        arxiv_id = url.rstrip("/").split("/")[-1]
        if not arxiv_id:
            return ""
        api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        response = self._http_get(api_url)
        root = ET.fromstring(response)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return ""
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        return f"{title}\n\n{summary}".strip()


    def _http_get(self, url: str) -> str:
        req = urllib_request.Request(url, headers={"User-Agent": "PM-OS-Orchestrator/3.0 (+https://example.local)"})
        try:
            with urllib_request.urlopen(req, timeout=15) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise ValueError(f"http status {status}")
                return resp.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise ValueError(f"http status {exc.code}") from exc
        except URLError as exc:
            raise ValueError(str(exc.reason)) from exc

    def _append_deepened_evidence(
        self,
        *,
        sig_path: Path,
        source_url: str | None,
        task_id: str | None,
        captured_at: str,
        fetch_status: str,
        excerpt: str,
    ) -> bool:
        content = sig_path.read_text(encoding="utf-8")
        if "## Deepened Evidence (L3)" in content and isinstance(source_url, str) and f"- source_url: {source_url}" in content:
            return False

        lines = [
            "",
            "## Deepened Evidence (L3)",
            f"- captured_at: {captured_at}",
            f"- source_url: {source_url or ''}",
            f"- fetch_status: {fetch_status}",
            "- evidence_excerpt:",
            f"  {excerpt}",
        ]
        updated = content.rstrip() + "\n" + "\n".join(lines) + "\n"
        updated = self._upsert_frontmatter(updated, captured_at=captured_at, task_id=task_id)
        sig_path.write_text(updated, encoding="utf-8")
        return True

    def _upsert_frontmatter(self, markdown: str, *, captured_at: str, task_id: str | None) -> str:
        if not markdown.startswith("---\n"):
            return markdown
        end_idx = markdown.find("\n---\n", 4)
        if end_idx == -1:
            return markdown

        frontmatter = markdown[4:end_idx]
        body = markdown[end_idx + 5 :]
        updates = {
            "deepened": "true",
            "deepened_at": captured_at,
            "deepening_task_id": task_id or "",
        }
        for key, value in updates.items():
            pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", flags=re.MULTILINE)
            line = f"{key}: {value}"
            if pattern.search(frontmatter):
                frontmatter = pattern.sub(line, frontmatter)
            else:
                frontmatter += f"\n{line}"
        return f"---\n{frontmatter}\n---\n{body}"

    def add_signal(
        self,
        *,
        source: str,
        signal_type: str,
        title: str | None = None,
        content: str | None = None,
        url: str | None = None,
        priority_score: float | None = None,
        impact_area: list[str] | None = None,
        timestamp: dt.datetime | None = None,
    ) -> SIGNAL:
        ts = timestamp or self.now_provider()
        signal_id = self._next_id("SIG", ts.date(), self.signals.read_all())
        signal = SIGNAL(
            id=signal_id,
            source=source,
            type=signal_type,
            timestamp=ts,
            title=title,
            content=content,
            url=url,
            priority_score=priority_score,
            impact_area=impact_area,
        )
        self.signals.append(signal.to_dict())
        return signal

    def top_signals(self, limit: int = 3) -> list[SIGNAL]:
        items = [SIGNAL.from_dict(row) for row in self.signals.read_all()]
        items.sort(
            key=lambda s: (
                s.priority_score if s.priority_score is not None else -1.0,
                s.timestamp,
            ),
            reverse=True,
        )
        return items[:limit]

    def generate_action(
        self,
        *,
        goal: str | None = None,
        action_type: str = "strategic_design",
        signal_id: str | None = None,
    ) -> ACTION_TASK:
        selected_signal = self._select_signal(signal_id)
        task_id = self._next_id("ACT", self.now_provider().date(), self.tasks.read_all())

        resolved_goal = goal or f"Respond to signal: {selected_signal.title or selected_signal.id}"
        task = ACTION_TASK(
            id=task_id,
            type=action_type,
            goal=resolved_goal,
            context=selected_signal.content,
            deliverables=[f"Action memo for {selected_signal.id}"],
            status="pending",
            created_at=self.now_provider(),
        )
        self.tasks.append(task.to_dict())

        signal_rows = self.signals.read_all()
        for row in signal_rows:
            if row.get("id") == selected_signal.id:
                row["linked_action_id"] = task.id
        self.signals.rewrite_all(signal_rows)

        self.writebacks.append(
            {
                "action_id": task.id,
                "status": "pending",
                "created_at": self.now_provider().isoformat(),
            }
        )

        return task

    def apply_writeback(
        self,
        *,
        action_id: str | None = None,
        artifact_kind: str = "lti",
        human_approved: bool = False,
        publish_intent: str | None = None,
        rti_intent: str | None = None,
    ) -> dict[str, Any]:
        task = self._resolve_task(action_id)
        artifact_kind = artifact_kind.lower()

        if artifact_kind == "lti":
            lti_id = self._existing_lti_id_for_action(task.id) or self._next_lti_id()
            lti_node = LTI_NODE(
                id=lti_id,
                title=task.goal,
                series="LTI-1.x",
                status="under_review",
                summary=task.context,
                linked_evidence=[task.id],
                published_at=self.now_provider().date(),
            )
            self.lti_nodes.append(lti_node.to_dict())
            written_path = write_lti_markdown(
                self.vault_root,
                lti_node,
                task.id,
                updated_at=self.now_provider().replace(microsecond=0).isoformat(),
                human_approved=human_approved,
                publish_intent=publish_intent,
            )
            payload = lti_node.to_dict()
            payload["id"] = lti_node.id
        elif artifact_kind == "rti":
            rti_id = self._next_rti_id()
            rti_node = RTI_NODE(
                id=rti_id,
                title=task.goal,
                status="under_review",
                linked_evidence=[task.id],
            )
            self.rti_nodes.append(rti_node.to_dict())
            written_path = write_rti_markdown(
                self.vault_root,
                rti_node,
                updated_at=self.now_provider().replace(microsecond=0).isoformat(),
                human_approved=human_approved,
                rti_intent=rti_intent,
            )
            payload = rti_node.to_dict()
            payload["id"] = rti_node.id
        else:
            raise ValueError(f"Unsupported artifact kind: {artifact_kind}")

        self.writebacks.append(
            {
                "action_id": task.id,
                "status": "applied",
                "artifact_kind": artifact_kind,
                "artifact_id": payload["id"],
                "human_approved": human_approved,
                "applied_at": self.now_provider().isoformat(),
            }
        )
        payload["written_path"] = str(written_path)
        return payload

    def create_gate_decision(
        self,
        *,
        signal_id: str,
        decision: str,
        priority: str,
        reason: str | None = None,
        next_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        signal = self._select_signal(signal_id)
        now = self.now_provider()
        decision_id = self._next_decision_id(now.date())

        resolved_reason = (reason or "No reason provided.").strip()
        resolved_actions = [item.strip() for item in (next_actions or []) if item.strip()]
        if not resolved_actions:
            resolved_actions = DEFAULT_NEXT_ACTIONS[decision]

        signal_summary = _excerpt(signal.content, limit=280) or signal.title or signal.id
        written_path = write_gate_decision(
            self.vault_root,
            decision_id=decision_id,
            signal_id=signal.id,
            decision=decision,
            priority=priority,
            decision_date=now.date(),
            reason=resolved_reason,
            next_actions=resolved_actions,
            signal_summary=signal_summary,
        )

        index_rows = self._read_decision_index()
        index_entry = {
            "decision_id": decision_id,
            "signal_id": signal.id,
            "decision": decision,
            "priority": priority,
            "created_at": now.isoformat(),
        }
        index_rows.append(index_entry)
        self._write_decision_index(index_rows)

        deepening_task_created = False
        deepening_task_id: str | None = None
        signal_updated = False

        if decision == "approved":
            deepening_task_id = self._find_existing_deepening_task_id(signal.id)
            if deepening_task_id is None:
                deepening_task_id = f"ACT-DEEPEN-{signal.id}"
                self.tasks.append(
                    {
                        "id": deepening_task_id,
                        "type": "deepening",
                        "signal_id": signal.id,
                        "goal": f"Fetch full evidence for signal {signal.id}",
                        "context": _excerpt(signal.content, limit=280) or signal.title or signal.id,
                        "status": "pending",
                        "created_at": now.isoformat(),
                        "auto_generated": True,
                    }
                )
                deepening_task_created = True

            signal_rows = self.signals.read_all()
            for row in signal_rows:
                if row.get("id") != signal.id:
                    continue
                if row.get("gate_status") == "approved":
                    break
                row["gate_status"] = "approved"
                row["gate_decision_id"] = decision_id
                row["deepening_task_id"] = deepening_task_id
                self.signals.rewrite_all(signal_rows)
                signal_updated = True
                break

        rejection_payload: dict[str, Any] = {}
        if decision == "reject":
            rejection_payload = self.handle_rejection(
                signal_id=signal.id,
                decision_id=decision_id,
                decision_reason=resolved_reason,
            )

        l5_created: list[dict[str, Any]] = []
        if decision == "approved":
            try:
                l5_created = route_after_gate_decision(decision_id, self.data_dir, self.vault_root)
            except (FileNotFoundError, NotADirectoryError) as exc:
                l5_created = [{"error": f"path error: {exc}"}]
            except OSError as exc:
                l5_created = [{"error": f"os error: {exc}"}]
            except Exception as exc:  # noqa: BLE001
                l5_created = [{"error": str(exc)}]

            lti_draft_id = next(
                (item.get("id") for item in l5_created if item.get("type") == "lti_draft"),
                None,
            )
            if not any("error" in item for item in l5_created):
                self._mark_signal_decided(signal.id, lti_draft_id)

        return {
            **index_entry,
            "reason": resolved_reason,
            "next_actions": resolved_actions,
            "written_path": str(written_path),
            "deepening_task_created": deepening_task_created,
            "deepening_task_id": deepening_task_id,
            "signal_updated": signal_updated,
            "l5_created": l5_created,
            **rejection_payload,
        }

    def _mark_signal_decided(self, signal_id: str, lti_draft_id: str | None) -> bool:
        if not signal_id:
            return False
        rows = self.signals.read_all()
        updated = False
        for row in rows:
            if row.get("id") == signal_id:
                row["lifecycle_status"] = "decided"
                if lti_draft_id:
                    row["lti_draft_id"] = lti_draft_id
                updated = True
                break
        if updated:
            self.signals.rewrite_all(rows)
        return updated

    def handle_rejection(self, *, signal_id: str, decision_id: str, decision_reason: str) -> dict[str, Any]:
        signal = self._select_signal(signal_id)
        now = self.now_provider().replace(microsecond=0)
        now_iso = now.isoformat()

        cos_index = self._read_cos_index()
        for entry in cos_index:
            if entry.get("decision_id") == decision_id:
                return {
                    "cos_id": entry["cos_id"],
                    "pattern_key": entry["pattern_key"],
                    "linked_rti": entry.get("linked_rti"),
                    "linked_rti_proposal": entry.get("linked_rti_proposal"),
                }

        pattern_key = self._compute_pattern_key(signal.to_dict(), decision_reason)
        cos_id = self._next_case_id(now.date(), cos_index)
        cos_path = self.vault_root / "06_Archive" / "COS" / f"{cos_id}.md"
        if cos_path.exists():
            raise FileExistsError(f"COS file already exists: {cos_path}")

        lines = [
            "---",
            f"id: {cos_id}",
            f"signal_id: {signal.id}",
            f"decision_id: {decision_id}",
            f"pattern_key: {pattern_key}",
            "impact_area:",
        ]
        impact_area = sorted(signal.impact_area or [])
        if impact_area:
            lines.extend([f"  - {item}" for item in impact_area])
        else:
            lines.append("[]")
        lines.extend(
            [
                f"reason: {self._yaml_safe(decision_reason)}",
                f"created_at: {now_iso}",
                "immutable: true",
                "---",
                "",
                "# COS Case",
                "",
                "## Signal Summary",
                _excerpt(signal.content, limit=280) or signal.title or signal.id,
                "",
                "## Rejection Reason",
                decision_reason,
                "",
                "## Pattern Key",
                pattern_key,
                "",
            ]
        )
        self._write_atomic(cos_path, "\n".join(lines))

        entry = {
            "cos_id": cos_id,
            "signal_id": signal.id,
            "decision_id": decision_id,
            "pattern_key": pattern_key,
            "created_at": now_iso,
            "linked_rti": None,
            "linked_rti_proposal": None,
        }
        cos_index.append(entry)
        trigger_payload = self._apply_rule_of_three(pattern_key=pattern_key, cos_index=cos_index, now=now)
        self._write_cos_index(cos_index)

        return {
            "cos_id": cos_id,
            "pattern_key": pattern_key,
            **trigger_payload,
        }

    def _apply_rule_of_three(self, *, pattern_key: str, cos_index: list[dict[str, Any]], now: dt.datetime) -> dict[str, Any]:
        matches = [entry for entry in cos_index if entry.get("pattern_key") == pattern_key]
        if len(matches) < 3:
            return {"linked_rti_proposal": None, "rti_triggered": False}

        linked_existing = next((entry.get("linked_rti_proposal") for entry in matches if entry.get("linked_rti_proposal")), None)
        if isinstance(linked_existing, str):
            return {"linked_rti_proposal": linked_existing, "rti_triggered": False}

        proposal_id = check_rule_of_three_and_propose_rti(
            pattern_key,
            self.data_dir,
            self.vault_root,
            cos_index=cos_index,
            now_iso=now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        if not proposal_id:
            return {"linked_rti_proposal": None, "rti_triggered": False}

        task_id = f"ACT-VALIDATE-{proposal_id}"
        if not any(task.get("id") == task_id for task in self.tasks.read_all()):
            self.tasks.append(
                {
                    "id": task_id,
                    "type": "rti_validation",
                    "goal": "Review RTI proposal due to repeated COS pattern",
                    "status": "pending",
                    "auto_generated": True,
                    "created_at": now.isoformat(),
                    "rti_proposal_id": proposal_id,
                    "trigger_pattern_key": pattern_key,
                }
            )

        for entry in matches:
            entry["linked_rti_proposal"] = proposal_id

        return {"linked_rti_proposal": proposal_id, "rti_triggered": True}

    def _compute_pattern_key(self, signal: dict[str, Any], decision_reason: str) -> str:
        normalized_reason = self._normalize_text(decision_reason)
        impact = sorted(str(item).strip().lower() for item in (signal.get("impact_area") or []) if str(item).strip())
        impact_key = ",".join(impact)
        return f"{normalized_reason}|{impact_key}"

    def _normalize_text(self, value: str) -> str:
        lowered = value.lower()
        no_punctuation = re.sub(r"[^a-z0-9\s]", " ", lowered)
        return " ".join(no_punctuation.split())

    def _next_case_id(self, day: dt.date, rows: list[dict[str, Any]]) -> str:
        date_key = day.strftime("%Y%m%d")
        matching = [row for row in rows if str(row.get("cos_id", "")).startswith(f"COS-{date_key}-")]
        return f"COS-{date_key}-{len(matching) + 1:03d}"

    def _next_rti_revision_id(self, day: dt.date) -> str:
        date_key = day.strftime("%Y%m%d")
        rti_dir = self.vault_root / "01_RTI"
        existing = list(rti_dir.glob(f"RTI-{date_key}-*.md")) if rti_dir.exists() else []
        return f"RTI-{date_key}-{len(existing) + 1:03d}"

    def _read_cos_index(self) -> list[dict[str, Any]]:
        if not self.cos_index_path.exists():
            return []
        return json.loads(self.cos_index_path.read_text(encoding="utf-8"))

    def _write_cos_index(self, rows: list[dict[str, Any]]) -> None:
        self.cos_index_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(self.cos_index_path, json.dumps(rows, indent=2))

    def _write_atomic(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.replace(tmp_name, path)

    def _yaml_safe(self, value: str) -> str:
        if re.match(r"^[A-Za-z0-9_./: -]+$", value):
            return value
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'

    def _find_existing_deepening_task_id(self, signal_id: str) -> str | None:
        for task in self.tasks.read_all():
            task_id = task.get("id")
            if not isinstance(task_id, str):
                continue
            if task_id == f"ACT-DEEPEN-{signal_id}":
                return task_id
            if task.get("type") == "deepening" and task.get("signal_id") == signal_id:
                return task_id

        for row in self.signals.read_all():
            if row.get("id") != signal_id:
                continue
            deepening_task_id = row.get("deepening_task_id")
            if isinstance(deepening_task_id, str):
                return deepening_task_id
        return None

    def _existing_lti_id_for_action(self, action_id: str) -> str | None:
        for writeback in reversed(self.writebacks.read_all()):
            if writeback.get("action_id") != action_id:
                continue
            lti_id = writeback.get("artifact_id")
            if isinstance(lti_id, str) and lti_id.startswith("LTI-"):
                return lti_id
        return None

    def _select_signal(self, signal_id: str | None) -> SIGNAL:
        signals = [SIGNAL.from_dict(row) for row in self.signals.read_all()]
        if not signals:
            raise ValueError("No signals found. Add a signal first.")

        if signal_id:
            for signal in signals:
                if signal.id == signal_id:
                    return signal
            available = [signal.id for signal in signals]
            preview = ", ".join(available[:10])
            suffix = "..." if len(available) > 10 else ""
            raise ValueError(
                "Signal not found: "
                f"{signal_id}. Available signal IDs: {preview}{suffix}. "
                "Verify the ID or list signals with `signal top` / `signal add`."
            )

        return self.top_signals(limit=1)[0]

    def _resolve_task(self, action_id: str | None) -> ACTION_TASK:
        tasks = [ACTION_TASK.from_dict(row) for row in self.tasks.read_all()]
        if not tasks:
            raise ValueError("No action tasks found. Generate an action first.")

        if action_id:
            for task in tasks:
                if task.id == action_id:
                    return task
            raise ValueError(f"Action task not found: {action_id}")

        pending_ids = {
            row["action_id"]
            for row in self.writebacks.read_all()
            if row.get("status") == "pending" and row.get("action_id")
        }
        for task in reversed(tasks):
            if task.id in pending_ids:
                return task
        return tasks[-1]

    def _next_id(self, prefix: str, day: dt.date, rows: list[dict[str, object]]) -> str:
        date_key = day.strftime("%Y%m%d")
        matching = [row for row in rows if str(row.get("id", "")).startswith(f"{prefix}-{date_key}-")]
        return f"{prefix}-{date_key}-{len(matching) + 1:03d}"

    def _next_lti_id(self) -> str:
        existing = [LTI_NODE.from_dict(row) for row in self.lti_nodes.read_all()]
        if not existing:
            return "LTI-1.0"
        minor_numbers: list[int] = []
        for node in existing:
            try:
                minor_numbers.append(int(node.id.split(".")[1]))
            except (IndexError, ValueError):
                continue
        next_minor = (max(minor_numbers) + 1) if minor_numbers else len(existing)
        return f"LTI-1.{next_minor}"

    def _next_rti_id(self) -> str:
        existing = [RTI_NODE.from_dict(row) for row in self.rti_nodes.read_all()]
        if not existing:
            return "RTI-1.0"

        minor_numbers: list[int] = []
        for node in existing:
            try:
                minor_numbers.append(int(node.id.split(".")[1]))
            except (IndexError, ValueError):
                continue
        next_minor = (max(minor_numbers) + 1) if minor_numbers else len(existing)
        return f"RTI-1.{next_minor}"

    def _read_decision_index(self) -> list[dict[str, Any]]:
        if not self.decision_index_path.exists():
            return []
        return json.loads(self.decision_index_path.read_text(encoding="utf-8"))

    def _write_decision_index(self, rows: list[dict[str, Any]]) -> None:
        self.decision_index_path.parent.mkdir(parents=True, exist_ok=True)
        self.decision_index_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _next_decision_id(self, day: dt.date) -> str:
        date_key = day.strftime("%Y%m%d")
        matching = [
            row
            for row in self._read_decision_index()
            if str(row.get("decision_id", "")).startswith(f"DEC-{date_key}-")
        ]
        return f"DEC-{date_key}-{len(matching) + 1:03d}"
