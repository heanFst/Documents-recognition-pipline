#!/usr/bin/env python3
"""
Inspect document conversion status.

View the document index, search by filename/hash, and check
conversion status for any document in the pipeline.

Usage:
    python scripts/inspect_document.py                        # list all
    python scripts/inspect_document.py --status FAILED        # filter by status
    python scripts/inspect_document.py --search paper         # search by name
    python scripts/inspect_document.py --hash <sha256_prefix> # search by hash prefix
    python scripts/inspect_document.py --path docs/raw/paper.pdf  # single file info
    python scripts/inspect_document.py --stats                # show statistics
    python scripts/inspect_document.py --verbose              # show full metadata
"""

import argparse
import json
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
    """Load all entries from index.jsonl."""
    index_file = PROJECT_ROOT / "docs" / "index.jsonl"
    if not index_file.exists():
        print(f"Index file not found: {index_file}")
        return []
    entries: list[dict] = []
    with open(index_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Warning: invalid JSON line skipped", file=sys.stderr)
    return entries


def truncate(s: str, max_len: int = 60) -> str:
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def print_entry(entry: dict, verbose: bool = False) -> None:
    """Print a single index entry."""
    if verbose:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        print()
        return

    status = entry.get("status", "?")
    src = entry.get("source_path", "?")
    sha = entry.get("sha256", "?")

    warnings = entry.get("warnings", [])
    warn_str = f" | {'; '.join(warnings)}" if warnings else ""

    # Status color mapping (text only)
    status_display = status

    print(f"  [{status_display:10s}] {src}")
    print(f"          sha256: {sha[:12]}...{sha[-8:]}{warn_str}")


def cmd_list(entries: list[dict], args: argparse.Namespace) -> None:
    """List entries with optional filtering."""
    if not entries:
        print("Index is empty. Run ingest_document.py first.")
        return

    # Filter by status
    if args.status:
        entries = [e for e in entries if e.get("status", "").upper() == args.status.upper()]
        if not entries:
            print(f"No entries with status '{args.status}'.")
            return

    # Filter by search
    if args.search:
        term = args.search.lower()
        entries = [
            e
            for e in entries
            if term in e.get("source_path", "").lower() or term in e.get("source_filename", "").lower()
        ]
        if not entries:
            print(f"No entries matching '{args.search}'.")
            return

    # Filter by hash prefix
    if args.hash:
        h = args.hash.lower()
        entries = [e for e in entries if e.get("sha256", "").startswith(h)]
        if not entries:
            print(f"No entries with SHA256 prefix '{args.hash}'.")
            return

    # Filter by path
    if args.path:
        p = args.path.replace("\\", "/").lower()
        entries = [
            e
            for e in entries
            if p in e.get("source_path", "").lower() or p in e.get("markdown_path", "").lower()
        ]
        if not entries:
            print(f"No entries matching path '{args.path}'.")
            return

    print(f"Found {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}:\n")
    for e in entries:
        print_entry(e, verbose=args.verbose)

    if not args.verbose:
        statuses = {}
        for e in entries:
            s = e.get("status", "?")
            statuses[s] = statuses.get(s, 0) + 1
        print(f"\n{'─' * 40}")
        print("Breakdown by status:")
        for s, count in sorted(statuses.items()):
            print(f"  {s:12s}: {count}")


def cmd_stats(entries: list[dict]) -> None:
    """Show comprehensive statistics."""
    if not entries:
        print("Index is empty.")
        return

    total = len(entries)
    statuses: dict[str, int] = {}
    converters: dict[str, int] = {}
    extensions: dict[str, int] = {}
    total_bytes = 0
    total_md_bytes = 0
    warnings_count = 0

    for e in entries:
        s = e.get("status", "?")
        statuses[s] = statuses.get(s, 0) + 1

        c = e.get("converter", "?")
        converters[c] = converters.get(c, 0) + 1

        ext = e.get("source_ext", "?")
        extensions[ext] = extensions.get(ext, 0) + 1

        total_bytes += e.get("source_size_bytes", 0)
        warnings_count += len(e.get("warnings", []))

        md_path = e.get("markdown_path", "")
        if md_path:
            p = PROJECT_ROOT / md_path
            if p.exists():
                total_md_bytes += p.stat().st_size

    print(f"\n{' Document Index Statistics ':=^50s}")
    print(f"  Total entries:      {total}")
    print(f"  Total source size:  {_fmt_bytes(total_bytes)}")
    print(f"  Total markdown:     {_fmt_bytes(total_md_bytes)}")
    print(f"  Total warnings:     {warnings_count}")

    print(f"\n  {'Status':16s} {'Count':>6s}")
    print(f"  {'─' * 22}")
    for s, count in sorted(statuses.items()):
        pct = count / total * 100
        print(f"  {s:16s} {count:6d} ({pct:5.1f}%)")

    print(f"\n  {'Extension':16s} {'Count':>6s}")
    print(f"  {'─' * 22}")
    for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
        print(f"  {ext:16s} {count:6d}")

    print(f"\n  {'Converter':20s} {'Count':>6s}")
    print(f"  {'─' * 26}")
    for c, count in sorted(converters.items(), key=lambda x: -x[1]):
        print(f"  {c:20s} {count:6d}")

    # Show failed entries
    failed = [e for e in entries if e.get("status") == "FAILED"]
    if failed:
        print(f"\n  Failed entries ({len(failed)}):")
        for e in failed:
            print(f"    - {e.get('source_path', '?')}: {e.get('error_message', '?')}")

    print(f"{'=' * 52}\n")


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect document conversion index and metadata."
    )
    parser.add_argument("--status", "-s", help="Filter by status (SUCCESS, FAILED, SKIPPED)")
    parser.add_argument("--search", help="Search entries by filename or path")
    parser.add_argument("--hash", help="Search by SHA256 prefix")
    parser.add_argument("--path", help="Show info for a specific file path")
    parser.add_argument("--stats", action="store_true", help="Show overall statistics")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full metadata JSON")
    args = parser.parse_args()

    entries = load_entries()

    if args.stats:
        cmd_stats(entries)
    elif args.status or args.search or args.hash or args.path:
        cmd_list(entries, args)
    else:
        # Default: list all
        cmd_list(entries, args)


if __name__ == "__main__":
    main()
