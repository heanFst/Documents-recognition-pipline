#!/usr/bin/env python3
"""
Clean up converted documents: remove markdown, metadata, and/or index entries.

WARNING: This permanently deletes files. Use --dry-run to preview.

Usage:
    python scripts/clean_document_cache.py --dry-run              # preview what would be deleted
    python scripts/clean_document_cache.py                        # remove all converted files
    python scripts/clean_document_cache.py --keep-failed          # keep failed entries
    python scripts/clean_document_cache.py --status FAILED        # only clean failed entries
    python scripts/clean_document_cache.py --path docs/raw/paper.pdf  # clean a specific file
    python scripts/clean_document_cache.py --stale                # remove entries with missing source files
"""

import argparse
import json
import os
import sys
from pathlib import Path


def find_project_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir, script_dir.parent, script_dir.parent.parent]:
        if (candidate / "docs").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()


def load_entries() -> list[dict]:
    index_file = PROJECT_ROOT / "docs" / "index.jsonl"
    if not index_file.exists():
        return []
    entries: list[dict] = []
    with open(index_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def save_entries(entries: list[dict]) -> None:
    index_file = PROJECT_ROOT / "docs" / "index.jsonl"
    with open(index_file, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")


def delete_file(path_str: str, dry_run: bool) -> bool:
    """Delete a file. Returns True if file existed and was (or would be) deleted."""
    if not path_str:
        return False
    p = PROJECT_ROOT / path_str
    if not p.exists():
        return False
    if dry_run:
        print(f"  [DRY] Would delete: {path_str}")
        return True
    try:
        p.unlink()
        print(f"  [DEL] Deleted: {path_str}")
        return True
    except OSError as e:
        print(f"  [ERR] Failed to delete {path_str}: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean up document conversion cache.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python scripts/clean_document_cache.py --dry-run
  python scripts/clean_document_cache.py --status FAILED
  python scripts/clean_document_cache.py --stale
  python scripts/clean_document_cache.py --path docs/raw/paper.pdf
        """,
    )
    parser.add_argument("--dry-run", "-n", action="store_true", help="Preview without deleting")
    parser.add_argument("--keep-failed", action="store_true", help="Keep failed entry files")
    parser.add_argument("--status", help="Only process entries with this status (SUCCESS, FAILED, SKIPPED)")
    parser.add_argument("--path", help="Clean a specific source file path")
    parser.add_argument("--stale", action="store_true", help="Remove entries whose source file is missing")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    entries = load_entries()
    if not entries:
        print("Index is empty. Nothing to clean.")
        return

    # Build list of entries to clean
    if args.path:
        target = args.path.replace("\\", "/")
        to_clean = [e for e in entries if e.get("source_path", "") == target]
        if not to_clean:
            # Try matching partial path
            to_clean = [e for e in entries if target in e.get("source_path", "")]
        if not to_clean:
            print(f"No entries found matching path '{args.path}'.")
            return
    elif args.status:
        status = args.status.upper()
        to_clean = [e for e in entries if e.get("status", "").upper() == status]
        if not to_clean:
            print(f"No entries with status '{args.status}'.")
            return
    elif args.stale:
        to_clean = []
        for e in entries:
            src = e.get("source_path", "")
            if src:
                src_path = PROJECT_ROOT / src
                if not src_path.exists():
                    to_clean.append(e)
        if not to_clean:
            print("No stale entries found (all source files exist).")
            return
    else:
        to_clean = entries[:]
        if args.keep_failed:
            to_clean = [e for e in to_clean if e.get("status") != "FAILED"]

    # Confirm
    print(f"Found {len(to_clean)} entr{'y' if len(to_clean) == 1 else 'ies'} to clean:\n")
    for e in to_clean:
        src = e.get("source_path", "?")
        status = e.get("status", "?")
        print(f"  [{status:10s}] {src}")

    if not args.dry_run and not args.yes:
        try:
            response = input(f"\nDelete associated markdown and metadata files? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = "n"
        if response not in ("y", "yes"):
            print("Aborted.")
            return

    # Delete associated files
    deleted_count = 0
    for e in to_clean:
        md_deleted = delete_file(e.get("markdown_path", ""), args.dry_run)
        meta_deleted = delete_file(e.get("metadata_path", ""), args.dry_run)

        # Also delete from docs/failed/ if present
        md_path = e.get("markdown_path", "")
        if md_path:
            failed_path = str(Path(md_path).name)
            delete_file(f"docs/failed/{failed_path}", args.dry_run)

        if md_deleted or meta_deleted:
            deleted_count += 1

    # Update index (remove cleaned entries)
    if not args.dry_run:
        cleaned_source_paths = {e.get("source_path", "") for e in to_clean}
        remaining = [e for e in entries if e.get("source_path", "") not in cleaned_source_paths]
        save_entries(remaining)
        print(f"\nIndex updated: {len(remaining)} entries remaining (removed {len(to_clean)}).")
    else:
        print(f"\n[Dry run complete] Would remove {len(to_clean)} entr{'y' if len(to_clean) == 1 else 'ies'}.")


if __name__ == "__main__":
    main()
