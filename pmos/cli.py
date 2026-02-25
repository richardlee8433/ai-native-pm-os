from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from avl.ops import EvidencePackStore
from cx_replay.replay_runner import run_fixture
from graph.ops import GraphStore
from revalidation.queue import write_queue_report
from promotion_router.manual_router import decide_manual_promotion, next_lti_id, write_rti_review
from orchestrator.vault_ops import write_lti_markdown
from pm_os_contracts.models import LTI_NODE
from validation_projects.ops import ValidationProjectStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PM-OS v4.1 CLI")
    parser.add_argument("--root", default=".", help="Repository root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    graph_parser = subparsers.add_parser("graph")
    graph_sub = graph_parser.add_subparsers(dest="graph_command", required=True)

    graph_create = graph_sub.add_parser("create")
    graph_create.add_argument("--type", required=True, choices=["concept", "skill", "playbook", "hypothesis", "evidence"])
    graph_create.add_argument("--title", required=True)
    graph_create.add_argument("--content")
    graph_create.add_argument("--validation-plan")
    graph_create.add_argument("--related", action="append", default=[])
    graph_create.add_argument("--tag", action="append", default=[])

    graph_list = graph_sub.add_parser("list")
    graph_show = graph_sub.add_parser("show")
    graph_show.add_argument("--id", required=True)

    graph_update = graph_sub.add_parser("update-status")
    graph_update.add_argument("--id", required=True)
    graph_update.add_argument("--status", required=True, choices=["exploring", "validation_ready", "validated", "archived"])

    avl_parser = subparsers.add_parser("avl")
    avl_sub = avl_parser.add_subparsers(dest="avl_command", required=True)
    avl_pack = avl_sub.add_parser("pack")
    avl_pack_sub = avl_pack.add_subparsers(dest="pack_command", required=True)
    avl_pack_create = avl_pack_sub.add_parser("create")
    avl_pack_create.add_argument("--title", required=True)
    avl_pack_validate = avl_pack_sub.add_parser("validate")
    avl_pack_validate.add_argument("--path", required=True)

    vp_parser = subparsers.add_parser("vp")
    vp_sub = vp_parser.add_subparsers(dest="vp_command", required=True)
    vp_init = vp_sub.add_parser("init")
    vp_init.add_argument("--title", required=True)
    vp_link_graph = vp_sub.add_parser("link-graph")
    vp_link_graph.add_argument("--id", required=True)
    vp_link_graph.add_argument("--graph-id", required=True, action="append")
    vp_link_evidence = vp_sub.add_parser("link-evidence")
    vp_link_evidence.add_argument("--id", required=True)
    vp_link_evidence.add_argument("--evidence-id", required=True, action="append")
    vp_status = vp_sub.add_parser("status")
    vp_status.add_argument("--id", required=True)
    vp_status.add_argument("--status", required=True, choices=["planned", "active", "blocked", "completed", "archived"])
    vp_promote = vp_sub.add_parser("promote")
    vp_promote.add_argument("--id", required=True)
    vp_promote.add_argument("--vault", default=None, help="Vault root directory override")

    lti_parser = subparsers.add_parser("lti")
    lti_sub = lti_parser.add_subparsers(dest="lti_command", required=True)
    lti_revalidation = lti_sub.add_parser("revalidation")
    lti_revalidation_sub = lti_revalidation.add_subparsers(dest="revalidation_command", required=True)
    lti_report = lti_revalidation_sub.add_parser("report")
    lti_report.add_argument("--vault", default=".vault_test", help="Vault root directory")

    cx_parser = subparsers.add_parser("cx")
    cx_sub = cx_parser.add_subparsers(dest="cx_command", required=True)
    cx_replay = cx_sub.add_parser("replay")
    cx_replay_sub = cx_replay.add_subparsers(dest="replay_command", required=True)
    cx_run = cx_replay_sub.add_parser("run")
    cx_run.add_argument("--fixture", required=True, help="Fixture id (filename without extension)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.command == "graph":
        store = GraphStore(root)
        if args.graph_command == "create":
            record = store.create(
                node_type=args.type,
                title=args.title,
                content=args.content,
                validation_plan=args.validation_plan,
                related_nodes=args.related,
                tags=args.tag,
            )
            print(json.dumps(record.to_dict()))
            return 0
        if args.graph_command == "list":
            print(json.dumps(store.list()))
            return 0
        if args.graph_command == "show":
            record = store.get(args.id)
            if not record:
                raise SystemExit(f"Graph node not found: {args.id}")
            print(json.dumps(record))
            return 0
        if args.graph_command == "update-status":
            record = store.update_status(node_id=args.id, status=args.status)
            print(json.dumps(record))
            return 0

    if args.command == "avl" and args.avl_command == "pack":
        store = EvidencePackStore(root)
        if args.pack_command == "create":
            record = store.create(title=args.title)
            print(json.dumps(record.to_index()))
            return 0
        if args.pack_command == "validate":
            result = store.validate(Path(args.path))
            print(json.dumps(result))
            return 0

    if args.command == "vp":
        store = ValidationProjectStore(root)
        if args.vp_command == "init":
            record = store.init(title=args.title)
            print(json.dumps(record.to_index()))
            return 0
        if args.vp_command == "link-graph":
            payload = store.link_graph(project_id=args.id, graph_ids=args.graph_id)
            print(json.dumps(payload))
            return 0
        if args.vp_command == "link-evidence":
            payload = store.link_evidence(project_id=args.id, evidence_ids=args.evidence_id)
            print(json.dumps(payload))
            return 0
        if args.vp_command == "status":
            payload = store.update_status(project_id=args.id, status=args.status)
            print(json.dumps(payload))
            return 0
        if args.vp_command == "promote":
            if not _promotion_enabled():
                print(json.dumps({"ok": False, "reason": "PMOS_USE_V41_PROMOTION is not enabled"}))
                return 2

            try:
                project = store.get(args.id)
            except ValueError as exc:
                print(json.dumps({"ok": False, "reason": str(exc)}))
                return 2

            graph_ids = project.get("linked_graph_nodes") or []
            evidence_ids = project.get("linked_evidence_packs") or []
            if not graph_ids or not evidence_ids:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "reason": "Validation project missing linked graph nodes or evidence packs",
                        }
                    )
                )
                return 2

            graph_store = GraphStore(root)
            graph_node = graph_store.get(graph_ids[0])
            if not graph_node:
                print(json.dumps({"ok": False, "reason": f"Graph node not found: {graph_ids[0]}"}))
                return 2

            evidence_store = EvidencePackStore(root)
            evidence_item = evidence_store.find_by_id(evidence_ids[0])
            if not evidence_item:
                print(json.dumps({"ok": False, "reason": f"Evidence pack not found: {evidence_ids[0]}"}))
                return 2

            evidence_path = root / evidence_item["path"]
            validation = evidence_store.validate(evidence_path)
            if not validation.get("ok"):
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "reason": "Evidence pack validation failed",
                            "missing": validation.get("missing", []),
                        }
                    )
                )
                return 2

            decision = decide_manual_promotion(evidence_pack_path=evidence_path)
            vault_root = _resolve_vault_root(root, args.vault)
            if decision["decision"] == "promote_to_lti":
                lti_id = next_lti_id(vault_root)
                now = dt.datetime.now(tz=dt.timezone.utc)
                revalidate_by = now.date() + dt.timedelta(days=28)
                lti_node = LTI_NODE(
                    id=lti_id,
                    title=decision.get("title") or graph_node.get("title") or f"Provisional LTI {lti_id}",
                    series="LTI-1.x",
                    status="under_review",
                    summary=decision.get("delta") or "Provisional LTI from AVL evidence.",
                    linked_evidence=[decision.get("pack_id", evidence_ids[0])],
                    validation_status="provisional",
                    source_graph_nodes=[graph_ids[0]],
                    validation_evidence_packs=[decision.get("pack_id", evidence_ids[0])],
                    revalidate_by=revalidate_by,
                    revalidate_status="pending",
                )
                path = write_lti_markdown(
                    vault_root,
                    lti_node,
                    source_task_id=project.get("id", "AVL-PROMOTION"),
                    updated_at=now.replace(microsecond=0).isoformat(),
                    human_approved=False,
                )
                payload = {"ok": True, "action": "lti_created", "lti_path": str(path), "lti_id": lti_id}
                governance_impact = decision.get("governance_impact", "")
                if governance_impact in {"review", "triggers"}:
                    review_path = write_rti_review(
                        vault_root=vault_root,
                        evidence_pack_id=decision.get("pack_id", evidence_ids[0]),
                        governance_impact=governance_impact,
                    )
                    payload["rti_review_path"] = str(review_path)
                print(json.dumps(payload))
                return 0

            if decision["decision"] == "rtireview":
                review_path = write_rti_review(
                    vault_root=vault_root,
                    evidence_pack_id=decision.get("pack_id", evidence_ids[0]),
                    governance_impact=decision.get("governance_impact", "review"),
                )
                print(json.dumps({"ok": True, "action": "rti_review_created", "proposal_path": str(review_path)}))
                return 0

            print(json.dumps({"ok": False, "action": "blocked", "reason": decision.get("reason", "blocked")}))
            return 2

    if args.command == "lti":
        if args.lti_command == "revalidation" and args.revalidation_command == "report":
            vault_root = root / args.vault
            output_path = write_queue_report(vault_root, root / "docs")
            payload = {"path": output_path.as_posix()}
            print(json.dumps(payload))
            return 0

    if args.command == "cx":
        if args.cx_command == "replay" and args.replay_command == "run":
            result = run_fixture(fixture_id=args.fixture, root=root)
            print(json.dumps(result))
            return 0

    parser.error("Unknown command")
    return 2


def _promotion_enabled() -> bool:
    env = os.getenv("PMOS_USE_V41_PROMOTION", "false").strip().lower()
    return env in {"1", "true", "yes", "on"}


def _resolve_vault_root(root: Path, override: str | None) -> Path:
    if override:
        candidate = Path(override)
        if candidate.is_absolute():
            return candidate
        return root / candidate
    env_root = os.getenv("PM_OS_VAULT_ROOT")
    if env_root:
        return Path(env_root)
    return root / ".vault_test"


if __name__ == "__main__":
    raise SystemExit(main())
