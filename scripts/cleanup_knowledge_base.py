#!/usr/bin/env python3
"""Safely inspect or remove selected development knowledge-base records."""

import argparse
import os
import sys
from typing import Iterable

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.main import rag_service


def documents() -> list[dict]:
    return rag_service.list_documents()


def selected_records(records: Iterable[dict], document_ids: list[str], remove_all: bool) -> list[dict]:
    if remove_all:
        return list(records)
    wanted = set(document_ids)
    return [record for record in records if record["document_id"] in wanted]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", action="append", default=[], help="Document ID to remove; may be repeated.")
    parser.add_argument("--all", action="store_true", dest="remove_all", help="Select every indexed document.")
    parser.add_argument("--confirm", action="store_true", help="Authorize deletion after reviewing the dry-run output.")
    args = parser.parse_args()

    records = documents()
    targets = selected_records(records, args.document_id, args.remove_all)
    print(f"Indexed logical documents: {len(records)}")
    for record in targets:
        print(f"SELECTED {record['document_id']} {record['filename']} ({record.get('chunk_count', 0)} chunks)")

    if not targets:
        print("No records selected. Nothing changed.")
        return 0
    if not args.confirm:
        print("Dry run only. Re-run with --confirm after reviewing the selected IDs.")
        return 0
    if not args.remove_all and not args.document_id:
        parser.error("Use --document-id or --all for a confirmed cleanup.")

    for record in targets:
        rag_service.delete_document(record["document_id"])
        source_path = record.get("source_path")
        if source_path and os.path.exists(source_path):
            os.remove(source_path)
        print(f"REMOVED {record['document_id']} {record['filename']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
