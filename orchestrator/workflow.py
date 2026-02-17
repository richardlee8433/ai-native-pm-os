from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Callable

from pm_os_contracts.models import ACTION_TASK, LTI_NODE, RTI_NODE, SIGNAL

from orchestrator.storage import JSONLStorage
from orchestrator.vault_ops import write_lti_markdown, write_rti_markdown


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
            raise ValueError(f"Signal not found: {signal_id}")

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
