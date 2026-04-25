#!/usr/bin/env python3
"""
Post-process MarkItDown output to improve structure and remove artifacts.

For PDF-derived markdown, this script:
  - Removes table-of-contents sections and scattered TOC artifact lines
  - Converts section-number patterns (e.g. "3.2.1 Compressed Sparse Attention")
    into proper markdown headings (### Compressed Sparse Attention)
  - Strips table artifacts like `# Shots`, `# Total Params`
  - Cleans up excessive blank lines

Usage:
    python scripts/postprocess_md.py docs/md/file.md            # in-place edit
    python scripts/postprocess_md.py docs/md/file.md -o out.md  # to new file
"""

import argparse
import re
import sys
from pathlib import Path


# ── Patterns ────────────────────────────────────────────────────────────────

# Section heading: "1 Introduction", "2.1 Architecture", "2.3.1 CSA", "3.5.4.1 Type"
# Trailing page numbers like " 21" are stripped from the title.
RE_SECTION = re.compile(
    r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?\s+([A-Z].+?)\s*\.?\s*$"
)

# TOC entry with dotted leader: "3.5.2 Title . . . . . . . 21"
RE_TOC_DOTTED = re.compile(r"^[\d.\s]+\s*[A-Z].*\.{3,}\s*(\d+)\s*$")

# TOC entry with trailing dot before page: "Inference Framework ."
RE_TOC_TRAILING_DOT = re.compile(r"^.+\s\.\s*$")

# Standalone page number line
RE_PAGE_NUM = re.compile(r"^\d{1,4}$")

# Known section titles that may appear without section numbers
KNOWN_SECTIONS: set[str] = {
    "Abstract", "Introduction", "Related Work", "Background",
    "Preliminaries", "Methodology", "Approach", "Method",
    "Experiments", "Experimental Setup", "Results",
    "Discussion", "Conclusion", "Conclusions",
    "Limitations", "Future Work", "References",
    "Appendix", "Appendices", "Contributions",
    "Broader Impact", "Ethics Statement",
    "Acknowledgments", "Acknowledgements",
    "Training Details", "Implementation Details",
    "Evaluation", "Setup", "Data",
}

# Table artifact headings (single # with short table-like text)
RE_TABLE_ARTIFACT = re.compile(
    r"^#\s+(?:"
    r"Shots|Activated\s+Params|Total\s+Params"
    r"|Tie|Win|Agent|RAG"
    r"|DS|Gem|Opus|V\d+"
    r"|DS%.*|Gem%.*|V4%.*"
    r"|Agent\s+Win|RAG\s+Win"
    r"|V4\s+win|V3\.2\s+win"
    r"|DS\s+win|Gem\s+win"
    r"|DS\s+Gem|Opus\s+.*"
    r")\s*$",
    re.IGNORECASE,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def is_toc_artifact(line: str) -> bool:
    """Check if a line is a TOC artifact (dotted leader, page number, etc.)."""
    s = line.strip()
    if not s:
        return False
    if RE_TOC_DOTTED.match(s):
        return True
    if RE_PAGE_NUM.match(s):
        return True
    if RE_TOC_TRAILING_DOT.match(s) and len(s) < 70:
        return True
    return False


def detect_toc_range(lines: list[str]) -> tuple[int, int]:
    """
    Detect the TOC section boundaries.

    Scans from a "Contents" header until real prose content begins.
    Returns (start, end) line indices, or (-1, -1) if no TOC found.
    """
    toc_start = -1
    toc_end = -1

    for i, line in enumerate(lines):
        s = line.strip()
        if s in ("Contents", "Table of Contents", "CONTENTS", "TABLE OF CONTENTS"):
            toc_start = i
            continue
        if toc_start >= 0 and toc_end < 0:
            if len(s) > 80 and not is_toc_artifact(line) and not s.startswith("Figure"):
                if re.search(r"[a-z]", s) and s.count(" ") > 5:
                    toc_end = i
                    break

    return (toc_start, toc_end)


def heading_level(groups: tuple) -> str:
    """Convert a section-number match to a markdown heading, stripping trailing page numbers."""
    levels = sum(1 for i in range(4) if groups[i] is not None)
    title = groups[4].strip().rstrip(".")
    # Strip trailing page number (e.g. "Title 21" → "Title")
    title = re.sub(r"\s+\d{1,4}$", "", title).strip()
    # Strip dotted leader artifacts (e.g. "Title . . . . . ." → "Title")
    title = re.sub(r"\s+\.\s*(?:\.\s*)*$", "", title).strip()
    # Strip trailing lone dots
    title = title.rstrip(".")
    md_level = min(levels + 1, 6)
    return f"{'#' * md_level} {title}"


# ── Processing steps ────────────────────────────────────────────────────────

def remove_toc_section(lines: list[str]) -> list[str]:
    """Remove the main table-of-contents section."""
    toc_start, toc_end = detect_toc_range(lines)
    if toc_start >= 0 and toc_end > toc_start:
        return lines[:toc_start] + lines[toc_end:]
    return lines


def remove_artifact_lines(lines: list[str]) -> list[str]:
    """Remove scattered TOC artifacts and table-artifact headings."""
    result = []
    for line in lines:
        stripped = line.strip()
        # Remove TOC artifacts
        if is_toc_artifact(line):
            continue
        # Remove single-# table artifact headings
        if RE_TABLE_ARTIFACT.match(stripped):
            continue
        # Also catch multi-word comparison table artifacts like "# Agent Win RAG Win Tie"
        if re.match(r"^#\s+[A-Z][a-z]*\s+[A-Za-z]+\s+[A-Za-z]+\s", stripped):
            continue
        # Catch `# ` lines with comparison table markers: "win", "tie", "%"
        if re.match(r"^#\s+.*\b(?:win|tie|Tie|Win)\b.*%", stripped):
            continue
        # Remove "# " followed by only caps/symbols shorter than 40 (table headers)
        if re.match(r"^#\s+[A-Z][A-Za-z/%\d\s]+$", stripped) and len(stripped) < 40:
            # If no real lowercase letters, it's probably a table header
            text = stripped[2:]
            words = text.split()
            caps_words = sum(1 for w in words if w.isupper() or (w[0].isupper() and w[1:].islower() if len(w) > 1 else True))
            if caps_words == len(words) and len(words) <= 4:
                continue
        result.append(line)
    return result


def convert_section_headings(lines: list[str]) -> list[str]:
    """Convert numbered section titles and known section names to markdown headings."""
    result = []
    for line in lines:
        m = RE_SECTION.match(line.strip())
        if m and len(line.strip()) < 120:
            result.append(heading_level(m.groups()))
        elif line.strip() in KNOWN_SECTIONS:
            # Promote known unnumbered section titles to ## headings
            result.append(f"## {line.strip()}")
        else:
            result.append(line)
    return result


def collapse_blank_lines(lines: list[str]) -> list[str]:
    """Collapse runs of >2 blank lines into 2."""
    result: list[str] = []
    blanks = 0
    for line in lines:
        if not line.strip():
            blanks += 1
            if blanks <= 2:
                result.append(line)
        else:
            blanks = 0
            result.append(line)
    return result


def postprocess(text: str) -> str:
    """
    Full post-processing pipeline:

    1. Detect and remove the main TOC section
    2. Remove scattered TOC artifacts and table-artifact headings
    3. Convert numbered section titles to markdown headings
    4. Collapse excessive blank lines
    """
    lines = text.split("\n")

    lines = remove_toc_section(lines)
    lines = convert_section_headings(lines)
    lines = remove_artifact_lines(lines)
    lines = collapse_blank_lines(lines)

    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-process MarkItDown output for better document structure."
    )
    parser.add_argument("input", help="Input markdown file")
    parser.add_argument("-o", "--output", help="Output file (default: in-place edit)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8", errors="replace")
    processed = postprocess(text)

    output_path = Path(args.output) if args.output else input_path
    output_path.write_text(processed, encoding="utf-8")

    original_lines = text.count("\n")
    new_lines = processed.count("\n")
    headings_before = len(re.findall(r"^#{1,6}\s", text, re.MULTILINE))
    headings_after = len(re.findall(r"^#{1,6}\s", processed, re.MULTILINE))

    print(f"Post-processed: {args.input}")
    print(f"  Lines: {original_lines} → {new_lines} ({new_lines - original_lines:+d})")
    print(f"  Headings: {headings_before} → {headings_after} (+{headings_after - headings_before})")


if __name__ == "__main__":
    main()
