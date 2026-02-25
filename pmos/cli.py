from __future__ import annotations

import argparse
import json
from pathlib import Path

from avl.ops import EvidencePackStore
from graph.ops import GraphStore
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

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
