<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/microsoft/markitdown/main/docs/images/logo-dark.svg">
    <img alt="Documents Recognition Pipeline" src="https://raw.githubusercontent.com/microsoft/markitdown/main/docs/images/logo-light.svg" width="60%">
  </picture>
</p>

<h1 align="center">Documents Recognition Pipeline</h1>

<p align="center">
  <b>Document to Markdown pipeline — powered by Microsoft MarkItDown.</b>
  <br>
  Batch convert PDF, DOCX, PPTX, XLSX, images & audio with automatic quality control.
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-directory-structure">Structure</a> •
  <a href="#-quality-assurance">Quality</a> •
  <a href="#-claude-code-integration">Claude Code</a> •
  <a href="#-troubleshooting">FAQ</a>
</p>

<p align="center">
  <b>Standardized document-to-Markdown pipeline</b> — powered by <a href="https://github.com/microsoft/markitdown">Microsoft MarkItDown</a>.
  <br>
  Converts PDF, DOCX, PPTX, XLSX, images, audio & more into clean, indexable Markdown.
  <br>
  Designed for AI-driven document analysis with automatic quality control.
</p>

---

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate
# Windows (Git Bash)
source .venv/Scripts/activate

# 2. Install MarkItDown with all dependencies
pip install 'markitdown[all]'

# 3. Convert a document
python scripts/ingest_document.py docs/raw/paper.pdf

# 4. View the index
python scripts/inspect_document.py --stats
```

---

## Usage

### Converting Documents

| Command | Description |
|---------|-------------|
| `python scripts/ingest_document.py docs/raw/file.pdf` | Convert a single file |
| `python scripts/ingest_document.py docs/raw/ --recursive` | Batch convert directory |
| `python scripts/ingest_document.py docs/raw/file.pdf --force` | Force re-conversion |
| `python scripts/ingest_document.py docs/raw/file.pdf --dry-run` | Preview only |

### Managing the Index

```bash
# List all documents
python scripts/inspect_document.py

# Filter by status
python scripts/inspect_document.py --status FAILED

# Search by filename
python scripts/inspect_document.py --search "deepseek"

# Show statistics
python scripts/inspect_document.py --stats

# Show full metadata JSON
python scripts/inspect_document.py --path docs/raw/paper.pdf --verbose
```

### Cleaning the Cache

```bash
python scripts/clean_document_cache.py --dry-run   # Preview deletions
python scripts/clean_document_cache.py              # Clean everything
python scripts/clean_document_cache.py --status FAILED   # Failed only
python scripts/clean_document_cache.py --stale           # Orphaned entries
```

---

## Directory Structure

```
.
├── docs/
│   ├── raw/              Source files (originals only)
│   ├── md/               Converted Markdown output
│   ├── meta/             Per-document metadata (JSON)
│   ├── assets/           Extracted images & attachments
│   ├── failed/           Copies of failed conversions
│   └── index.jsonl       Full document index (JSONL)
├── scripts/
│   ├── ingest_document.py       Conversion entry point
│   ├── inspect_document.py      Index viewer & search
│   ├── clean_document_cache.py  Cache cleanup utility
│   └── postprocess_md.py        Markdown structure enhancer
└── .claude/
    └── document_policy.md       Claude Code reading policy
```

### Output Naming

```
paper.pdf  →  paper.a1b2c3d4e5f6.md     (source_stem.sha256_prefix.md)
           →  paper.a1b2c3d4e5f6.json    (metadata)
```

The 12-character SHA256 prefix ensures uniqueness and change detection.

### Processing Pipeline

```
Source File
    │
    ▼
┌──────────────────────────────────────────────────┐
│  MarkItDown Conversion                           │
│  (CLI → API fallback if CLI fails)               │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│  Post-processing                                  │
│  • Convert section numbers to Markdown headings   │
│  • Strip TOC artifacts & page numbers             │
│  • Remove table-artifact headings                 │
│  • Promote known section titles (Introduction,    │
│    Related Work, Method, Conclusion, etc.)        │
└──────────────────────┬───────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│  Quality Control                                  │
│  • LOW_TEXT_EXTRACTION: <100 chars for >100KB src │
│  • POSSIBLE_ENCODING_OR_OCR_ERROR: garbled > 5%   │
│  • WEAK_STRUCTURE: missing ## heading hierarchy    │
│  • FAILED: empty or missing output                │
└──────────────────────┬───────────────────────────┘
                       ▼
              docs/md/ file + docs/index.jsonl
```

---

## Supported Formats

| Category | Formats |
|----------|---------|
| Documents | PDF, DOCX, PPTX, XLSX, XLS, CSV, EPUB |
| Web | HTML, HTM, XML, JSON |
| Text | TXT, MD |
| Images | PNG, JPG, JPEG, WebP, GIF |
| Audio | MP3, WAV |
| Archives | ZIP |

**Text-based** formats (TXT, MD, HTML, CSV, JSON, XML) are read **directly without conversion** — no pipeline overhead.

**Binary** formats (PDF, DOCX, PPTX, XLSX, images, audio) go through the full MarkItDown pipeline.

---

## Quality Assurance

### Automatic Checks

Each conversion runs these checks:

| Check | Condition | Flag |
|-------|-----------|------|
| LOW_TEXT_EXTRACTION | Markdown < 100 chars, source > 100 KB | ⚠️ warning |
| POSSIBLE_ENCODING_OR_OCR_ERROR | Garbled character ratio > 5% | ⚠️ warning |
| WEAK_STRUCTURE | PDF/DOCX/PPTX without \#\# heading hierarchy | ⚠️ warning |
| EMPTY_OUTPUT | Markdown is empty or missing | ❌ FAILED |

All warnings and errors are recorded in `docs/index.jsonl` and the per-document metadata JSON.

### Post-Processing

For PDF-derived Markdown, the pipeline automatically:

- **Detects section numbers** (`1.`, `2.1`, `3.2.1`) and converts them to `##`, `###`, `####` headings
- **Recognizes unnumbered section titles**: Abstract, Introduction, Related Work, Method, Conclusion, References, Appendix, etc.
- **Removes TOC artifacts**: Dotted leader lines, standalone page numbers, table of contents blocks
- **Filters table artifacts**: Strips `# Shots`, `# Total Params`, `# Win/Tie/%` lines from table output
- **Stops at References**: No further heading promotion after the references section

---

## Claude Code Integration

The `.claude/document_policy.md` file defines how Claude Code handles documents:

| Rule | Description |
|------|-------------|
| Don't read raw binaries | All binary docs go through MarkItDown first |
| Check the index | Look up `docs/index.jsonl` for conversion status |
| Read only Markdown | Access content from `docs/md/` only |
| Progressive reading | Long docs → read headings first, then target sections |
| Flag limitations | Tables, formulas, charts may need visual review |
| Cite sources | Always reference source filename and Markdown path |
| Handle failures | Check `error_message` in metadata JSON for FAILED status |

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| `ImportError` | Missing optional dependency | `pip install 'markitdown[all]'` |
| Empty or minimal output | Scanned PDF (no text layer) | Use OCR (Azure Document Intelligence, Tesseract) |
| Garbled text | Encoding mismatch / OCR quality | Flag for human review |
| `FAILED` in index | Corrupted or encrypted file | Check error_message in metadata JSON |
| Timeout | File too large | Split file or convert relevant portion |
| No headings in Markdown | PDF without structured text | Post-processing already handles most cases |

---

## License

This project is licensed under the **MIT License**.

### MarkItDown

<p align="left">
  <a href="https://github.com/microsoft/markitdown">
    <img src="https://img.shields.io/badge/powered%20by-MarkItDown-blue?logo=microsoft" alt="Powered by MarkItDown">
  </a>
</p>

This pipeline uses [Microsoft MarkItDown](https://github.com/microsoft/markitdown) (MIT License) as its core conversion engine. MarkItDown is a utility tool by Microsoft for converting various file formats to Markdown. The full license can be found in the [MarkItDown repository](https://github.com/microsoft/markitdown).

```
MIT License

Copyright (c) Microsoft Corporation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
...
```
