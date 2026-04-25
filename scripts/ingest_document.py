#!/usr/bin/env python3
"""
Document ingestion pipeline using Microsoft MarkItDown.

Converts raw documents (PDF, DOCX, PPTX, XLSX, images, audio, etc.)
to Markdown with metadata tracking, quality control, and indexing.

Usage:
    python scripts/ingest_document.py docs/raw/file.pdf
    python scripts/ingest_document.py docs/raw/ --recursive
    python scripts/ingest_document.py docs/raw/file.pdf --force
    python scripts/ingest_document.py docs/raw/file.pdf --dry-run
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Optional


# ── Supported file extensions ──────────────────────────────────────────────
SUPPORTED_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv",
    ".json", ".xml", ".html", ".htm",
    ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp3", ".wav",
    ".zip", ".epub",
}

EXT_GROUPS: dict[str, set[str]] = {
    "document": {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".epub"},
    "web": {".html", ".htm", ".xml", ".json"},
    "text": {".txt", ".md"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "audio": {".mp3", ".wav"},
    "archive": {".zip"},
}


# ── Project root detection ─────────────────────────────────────────────────
def find_project_root() -> Path:
    """Find the project root (directory containing scripts/ and docs/)."""
    script_dir = Path(__file__).resolve().parent
    # Walk up from scripts/ to find the project root
    for candidate in [script_dir, script_dir.parent, script_dir.parent.parent]:
        if (candidate / "docs").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    # Fallback to CWD
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()


# ── Path helpers ────────────────────────────────────────────────────────────
def rel(path: Path) -> str:
    """Convert an absolute path to a project-relative POSIX-style path."""
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace(os.sep, "/")
    except ValueError:
        return str(path).replace(os.sep, "/")


def abs_path(rel_str: str) -> Path:
    """Convert a project-relative path string back to an absolute path."""
    return (PROJECT_ROOT / rel_str).resolve()


def docs_dir(subdir: str = "") -> Path:
    """Return the docs/<subdir> directory, creating if needed."""
    d = PROJECT_ROOT / "docs" / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── SHA256 ──────────────────────────────────────────────────────────────────
def sha256_of(path: Path) -> str:
    """Compute SHA-256 digest of a file, streaming to handle large files."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192 * 256):
            h.update(chunk)
    return h.hexdigest()


# ── Index (index.jsonl) ────────────────────────────────────────────────────
def load_index() -> dict[str, dict]:
    """Load the full index. Returns dict keyed by source_path."""
    index_file = PROJECT_ROOT / "docs" / "index.jsonl"
    if not index_file.exists():
        return {}
    entries: dict[str, dict] = {}
    with open(index_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    src = entry.get("source_path", "")
                    if src:
                        entries[src] = entry
                except json.JSONDecodeError:
                    warnings.warn(f"Skipping invalid index line: {line[:80]}")
    return entries


def save_index(entries: dict[str, dict]) -> None:
    """Write the full index back to index.jsonl."""
    index_file = PROJECT_ROOT / "docs" / "index.jsonl"
    with open(index_file, "w", encoding="utf-8") as f:
        for entry in entries.values():
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def update_index(entry: dict) -> None:
    """Add or update a single entry in the index."""
    entries = load_index()
    src = entry.get("source_path", "")
    if src:
        entries[src] = entry
    save_index(entries)


# ── MarkItDown conversion ──────────────────────────────────────────────────
def convert_with_cli(input_path: Path, output_path: Path) -> tuple[bool, str]:
    """Try MarkItDown CLI. Returns (success, error_message)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "markitdown", str(input_path), "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return True, ""
        else:
            stderr = (result.stderr or "").strip()
            return False, f"CLI exited {result.returncode}: {stderr}"
    except FileNotFoundError:
        return False, "markitdown CLI not found"
    except subprocess.TimeoutExpired:
        return False, "CLI timed out after 300s"
    except Exception as e:
        return False, f"CLI error: {e}"


def convert_with_api(input_path: Path, output_path: Path) -> tuple[bool, str]:
    """Try MarkItDown Python API. Returns (success, error_message)."""
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(input_path))
        text = result.text_content
        if text is None:
            return False, "API returned None text_content"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        return True, ""
    except ImportError:
        return False, "markitdown package not installed"
    except Exception as e:
        return False, f"API error: {e}"


def convert_file(input_path: Path, output_path: Path) -> tuple[bool, str, str]:
    """
    Convert a single file using MarkItDown.
    Tries CLI first, falls back to Python API.
    Returns (success, error_message, converter_used).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Try CLI
    success, error = convert_with_cli(input_path, output_path)
    if success:
        return True, "", "markitdown-cli"

    # Fall back to API
    success, error = convert_with_api(input_path, output_path)
    if success:
        return True, "", "markitdown-api"

    return False, error, "markitdown-cli"


# ── Quality Control ─────────────────────────────────────────────────────────
def is_binary_ext(ext: str) -> bool:
    """Check if the extension is for a file type that produces text."""
    doc_like = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm", ".epub", ".zip", ".xml"}
    return ext.lower() in doc_like


def has_heading_structure(text: str) -> bool:
    """Check if markdown text contains heading markers."""
    return bool(re.search(r"^#{1,6}\s", text, re.MULTILINE))


REPLACEMENT_CHAR = "�"
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def garbled_ratio(text: str) -> float:
    """
    Estimate the proportion of problematic characters.
    Flags replacement chars, excess control chars, and non-printable sequences.
    """
    if not text:
        return 0.0
    n_replacement = text.count(REPLACEMENT_CHAR)
    n_control = len(CONTROL_CHAR_RE.findall(text))

    # Count chars outside typical printable ranges for academic text
    junk = n_replacement + n_control
    return junk / len(text)


def run_qc(source_path: Path, md_path: Path, ext: str) -> list[str]:
    """Run quality checks on the converted markdown. Returns list of warnings."""
    warnings_list: list[str] = []

    if not md_path.exists():
        warnings_list.append("FAILED: markdown file does not exist")
        return warnings_list

    text = md_path.read_text(encoding="utf-8", errors="replace")
    source_size = source_path.stat().st_size if source_path.exists() else 0

    # QC-D: Empty output
    if not text.strip():
        warnings_list.append("FAILED: markdown is empty")
        return warnings_list

    # QC-B: Low text extraction
    if len(text) < 100 and source_size > 100 * 1024:
        warnings_list.append("warning: LOW_TEXT_EXTRACTION")

    # QC-C: Possible encoding/OCR errors
    ratio = garbled_ratio(text)
    if ratio > 0.05:
        warnings_list.append(f"warning: POSSIBLE_ENCODING_OR_OCR_ERROR (garbled ratio {ratio:.3f})")

    # QC-E: Weak structure for document types
    if ext.lower() in {".pdf", ".pptx", ".docx"} and not has_heading_structure(text):
        warnings_list.append("warning: WEAK_STRUCTURE")

    return warnings_list


# ── Main processing ─────────────────────────────────────────────────────────
def build_metadata(
    source_path: Path,
    sha256: str,
    md_path: Path,
    meta_path: Path,
    status: str,
    converter: str = "",
    error_message: str = "",
    warnings: list[str] | None = None,
) -> dict:
    """Build a metadata dict for a document."""
    return {
        "source_path": rel(source_path),
        "source_filename": source_path.name,
        "source_ext": source_path.suffix.lower(),
        "source_size_bytes": source_path.stat().st_size,
        "sha256": sha256,
        "markdown_path": rel(md_path) if md_path.exists() else "",
        "metadata_path": rel(meta_path),
        "converted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "converter": converter,
        "converter_command": "markitdown",
        "status": status,
        "error_message": error_message,
        "warnings": warnings or [],
    }


def process_single_file(
    source_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[str, str]:
    """
    Process a single source file.
    Returns (status, sha256_prefix).
    """
    ext = source_path.suffix.lower()
    sha256_digest = sha256_of(source_path)
    sha256_prefix = sha256_digest[:12]

    # Build output paths: md/{first2}/{rest}.md to avoid flat directory issues
    stem = source_path.stem
    safe_stem = "".join(c if c.isalnum() or c in "._- " else "_" for c in stem)

    md_filename = f"{safe_stem}.{sha256_prefix}.md"
    meta_filename = f"{safe_stem}.{sha256_prefix}.json"

    md_path = docs_dir("md") / md_filename
    meta_path = docs_dir("meta") / meta_filename
    raw_rel = rel(source_path)

    # ── Check if already converted ──
    index = load_index()
    existing = index.get(raw_rel)

    if existing and existing.get("sha256") == sha256_digest and not force:
        if dry_run:
            print(f"[SKIP]  {raw_rel} — SHA256 unchanged, use --force to re-convert")
        else:
            # Ensure files still exist
            if md_path.exists():
                print(f"[SKIP]  {raw_rel} — SHA256 unchanged")
                return "SKIPPED", sha256_prefix
            else:
                print(f"[WARN]  {raw_rel} — SHA256 matches but MD missing, re-converting")

    if dry_run:
        print(f"[DRY]   {raw_rel} -> {rel(md_path)}")
        print(f"        sha256: {sha256_digest}")
        return "DRY_RUN", sha256_prefix

    # ── Convert ──
    print(f"[CONV]  {raw_rel} ... ", end="", flush=True)
    success, error_msg, converter_used = convert_file(source_path, md_path)

    if not success:
        print("FAILED")
        print(f"        Error: {error_msg}")
        # Write metadata file even for failures
        meta = build_metadata(
            source_path=source_path,
            sha256=sha256_digest,
            md_path=md_path,
            meta_path=meta_path,
            status="FAILED",
            converter=converter_used,
            error_message=error_msg,
        )
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        update_index(meta)

        # Copy to failed/ also
        failed_path = docs_dir("failed") / md_filename
        if md_path.exists():
            shutil.copy2(md_path, failed_path)

        return "FAILED", sha256_prefix

    # ── Quality Control ──
    qc_warnings = run_qc(source_path, md_path, ext)
    for w in qc_warnings:
        if w.startswith("FAILED"):
            status = "FAILED"
            error_msg = w
            break
    else:
        status = "SUCCESS"

    for w in qc_warnings:
        if not w.startswith("FAILED"):
            print(f"\n        {w}")

    print("OK" if status == "SUCCESS" else "FAILED (QC)")

    # ── Write metadata ──
    meta = build_metadata(
        source_path=source_path,
        sha256=sha256_digest,
        md_path=md_path,
        meta_path=meta_path,
        status=status,
        converter=converter_used,
        error_message=error_msg if status == "FAILED" else "",
        warnings=[w for w in qc_warnings if not w.startswith("FAILED")],
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    update_index(meta)

    if status == "FAILED":
        failed_path = docs_dir("failed") / md_filename
        if md_path.exists():
            shutil.copy2(md_path, failed_path)

    # ── Copy assets (images etc.) ──
    # MarkItDown extracts images alongside the output by default.
    # We leave them in docs/md/ for simplicity.

    return status, sha256_prefix


def collect_files(paths: list[str], recursive: bool) -> list[Path]:
    """Collect all supported files from the given paths."""
    collected: list[Path] = []

    for p in paths:
        p_path = Path(p)
        if not p_path.exists():
            print(f"[ERROR] Path does not exist: {p}", file=sys.stderr)
            continue

        if p_path.is_file():
            if p_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected.append(p_path)
            else:
                print(f"[WARN]  Unsupported extension: {p_path.suffix} — {p_path.name}", file=sys.stderr)

        elif p_path.is_dir():
            if recursive:
                for f in sorted(p_path.rglob("*")):
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                        collected.append(f)
            else:
                for f in sorted(p_path.iterdir()):
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                        collected.append(f)

    return collected


def print_summary(results: list[tuple[str, str]]) -> None:
    """Print a summary of all results."""
    total = len(results)
    success = sum(1 for s, _ in results if s == "SUCCESS")
    skipped = sum(1 for s, _ in results if s == "SKIPPED")
    failed = sum(1 for s, _ in results if s == "FAILED")
    dry_run_count = sum(1 for s, _ in results if s == "DRY_RUN")

    if total == 0:
        print("No files processed.")
        return

    print(f"\n{'=' * 40}")
    print(f"Summary: {total} files")
    if success:
        print(f"  SUCCESS: {success}")
    if skipped:
        print(f"  SKIPPED: {skipped}")
    if failed:
        print(f"  FAILED:  {failed}")
    if dry_run_count:
        print(f"  DRY RUN: {dry_run_count}")
    print(f"{'=' * 40}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown using MarkItDown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python scripts/ingest_document.py docs/raw/paper.pdf
  python scripts/ingest_document.py docs/raw/ --recursive
  python scripts/ingest_document.py docs/raw/paper.pdf --force
  python scripts/ingest_document.py docs/raw/paper.pdf --dry-run
        """,
    )
    parser.add_argument("input", nargs="+", help="Input file(s) or directory")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursively scan directories")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-conversion even if SHA256 matches")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done without converting")

    args = parser.parse_args()

    # Ensure doc directories exist
    docs_dir("raw")
    docs_dir("md")
    docs_dir("meta")
    docs_dir("assets")
    docs_dir("failed")

    files = collect_files(args.input, recursive=args.recursive)

    if not files:
        print("No supported files found.")
        sys.exit(0)

    results: list[tuple[str, str]] = []
    for f in files:
        status, prefix = process_single_file(
            source_path=f,
            force=args.force,
            dry_run=args.dry_run,
        )
        results.append((status, prefix))

    print_summary(results)

    # Exit with non-zero if any files failed
    if any(s == "FAILED" for s, _ in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
