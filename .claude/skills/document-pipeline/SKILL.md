---
name: document-pipeline
description: >
  Full document intelligence pipeline using MarkItDown. Use this skill whenever
  the user asks to read, analyze, summarize, or extract content from any document
  file — PDF, DOCX, PPTX, XLSX, XLS, CSV, images (PNG/JPG/WebP), HTML, EPUB,
  audio files, or ZIP archives. Also trigger when the user mentions "帮我读一下",
  "分析这个文件", "这个文档里写了什么", "总结一下这份报告", "convert this document",
  "提取这个表格", or references files in docs/raw/. This skill converts binary
  documents to Markdown first, then reads the Markdown — never reads raw binaries.
  Includes OCR awareness for scanned PDFs and image-only content, automatic
  quality checks, and progressive reading for long documents.
compatibility: Python 3.10+, markitdown, scripts/ingest_document.py, scripts/inspect_document.py
---

# Document Pipeline Skill

## Core Principle

**Never read raw binary documents directly.** Binary formats (PDF, DOCX, PPTX, XLSX, images, audio) must be converted to Markdown via MarkItDown before analysis. Text-based formats (TXT, MD, HTML, CSV, JSON, XML) can be read directly without conversion — they are already readable.

---

## Format Classification

Determine the format type before deciding the reading strategy:

| Category | Extensions | Strategy |
|----------|-----------|----------|
| Text-based (read directly) | `.txt` `.md` `.html` `.htm` `.csv` `.json` `.xml` | Read with Read tool, no pipeline needed |
| Binary (must convert) | `.pdf` `.docx` `.pptx` `.xlsx` `.xls` `.png` `.jpg` `.jpeg` `.webp` `.gif` `.mp3` `.wav` `.zip` `.epub` | Run MarkItDown pipeline first |

## Workflow

### Step 0: Verify environment

Before processing any binary document, ensure MarkItDown is available:

```bash
# Check venv exists
test -f .venv/Scripts/activate || test -f .venv/bin/activate
# Check markitdown is installed
python -m markitdown --version
```

If missing, run:
```bash
python -m venv .venv
source .venv/Scripts/activate  # or .venv/bin/activate on Linux/Mac
pip install 'markitdown[all]'
```

### Step 1: Locate the document

The user may reference a document by:
- Full path: `docs/raw/paper.pdf`
- Filename only: `paper.pdf` — search `docs/raw/` recursively
- Partial name: `那个关于XX的报告` — search by filename keywords
- Vague reference: "我下载的那个 PDF" — list recent files in `docs/raw/`

Use `find`/`ls` and the existing `inspect_document.py` to locate and check status:

```bash
python scripts/inspect_document.py --search <keyword>
```

### Step 2: Decide strategy by format type

Check the file extension and choose the appropriate path:

**Text-based formats** (`.txt` `.md` `.html` `.htm` `.csv` `.json` `.xml`):
- No conversion needed — read the file directly with the Read tool
- Skip Steps 3-4, go directly to Step 5 (Analyze and respond)
- For very large text files, use progressive reading (read first 50 lines to get structure, then target specific sections)

**Binary formats** (`.pdf` `.docx` `.pptx` `.xlsx` `.xls` `.png` `.jpg` `.jpeg` `.webp` `.gif` `.mp3` `.wav` `.zip` `.epub`):
- Proceed to Step 3 to check index and convert

### Step 3: Check index for existing conversion

For binary documents only, check `docs/index.jsonl` for a prior conversion:

```
# Example index entry:
{"source_path": "docs/raw/paper.pdf", "status": "SUCCESS", "markdown_path": "docs/md/paper.a1b2c3d4e5f6.md", ...}
```

If status is `SUCCESS` and the markdown file exists: proceed to Step 4.
If status is `FAILED`: check `docs/meta/<hash>.json` for `error_message`, fix the issue, then re-convert.
If not in index at all: proceed to Step 3b.

### Step 3b: Convert binary document with MarkItDown

Run the ingestion pipeline:

```bash
python scripts/ingest_document.py docs/raw/<file>
```

The script handles:
- SHA256 deduplication (skips if unchanged)
- CLI-first, API-fallback conversion
- Quality checks (low text extraction, garbled text, weak structure)
- Metadata generation and index update

If conversion fails, check the metadata JSON in `docs/meta/` for the `error_message` field.

### Step 4: Read the converted Markdown (binary docs only)

Read the markdown file at the path indicated by `markdown_path` in the index entry (under `docs/md/`).

**Progressive reading for long documents:**

1. First read the first ~50 lines to get the document structure (headings)
2. If the document has clear section headings, read only the relevant sections
3. Use targeted line ranges or grep for specific topics
4. If reading the whole file is safe (< 500 lines), read it in one pass

```
# Read structure (first 50 lines)
head -n 50 docs/md/<file>.md

# Search for specific topic
grep -n -i "topic" docs/md/<file>.md

# Read specific section by line range
# (use Read tool with offset/limit)
```

### Step 5: Analyze and respond

When presenting information from the document, always:
1. Cite the source: `docs/raw/<filename>` and `docs/md/<hash>.md`
2. Note structural elements found: headings, tables, lists, formulas
3. Flag content that may need visual review: images, complex tables, math formulas, charts
4. Check the `warnings` field in the index entry for quality flags:
   - `LOW_TEXT_EXTRACTION` → text may be incomplete
   - `POSSIBLE_ENCODING_OR_OCR_ERROR` → text may be garbled
   - `WEAK_STRUCTURE` → document structure may not be preserved

---

## OCR / Scanned Document Handling

### Detection

After conversion, check for signs that the document is a scan:
1. Markdown is very short relative to file size (Low Text Extraction warning)
2. Content is garbled (Possible Encoding or OCR Error warning)
3. PDF has no selectable text layer (check with: `pdfinfo` or `pdftotext`)

### Strategy

For scanned/OCR documents:
1. First try MarkItDown (may fail or produce minimal text)
2. If insufficient, inform the user:
   > "This appears to be a scanned document. MarkItDown extracted minimal text. You may need a dedicated OCR tool (Azure Document Intelligence, Tesseract, or manual transcription)."
3. Offer to check the warning details: `python scripts/inspect_document.py --path docs/raw/<file> --verbose`

---

## Image Analysis

For images (PNG, JPG, JPEG, WebP, GIF):
1. MarkItDown will attempt OCR on text within images
2. After conversion, read the markdown output
3. **Important**: Images may contain visual information (charts, diagrams, screenshots) that OCR cannot capture. Always mention: *"Some visual content may require direct inspection — I've extracted the text found in this image."*
4. You CAN read the image directly using the Read tool (images are supported), but prefer the pipeline approach first

---

## Table and Spreadsheet Handling

For **XLSX/XLS** (binary format):
1. MarkItDown converts tables to Markdown table format
2. After conversion, read the markdown to get the tabular data
3. For large spreadsheets, the conversion may be incomplete — check warnings
4. If the user needs to analyze data (filter, sort, compute), suggest exporting to CSV or using Python/pandas directly

For **CSV** (text-based format):
- Read the file directly — no conversion needed
- Use Python/pandas for structured analysis if the file is large

---

## Failure Recovery

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| `Error: module not found` | Missing dependency | Run `pip install 'markitdown[all]'` |
| Empty markdown output | Scanned PDF / corrupted file | Flag as OCR-required or check file |
| Garbled text (high warning level) | Encoding mismatch / OCR quality | Flag for human review |
| Timeout | File too large | Suggest splitting the file |
| `FAILED` in index | Various | Read metadata error_message and advise |

---

## Quality Checklist

Before responding with document content, verify:

**For binary documents (PDF, DOCX, PPTX, XLSX, images, audio):**
- [ ] Did you convert via MarkItDown first (not read the raw binary)?
- [ ] Did you check the index for warnings (LOW_TEXT_EXTRACTION, WEAK_STRUCTURE, etc.)?
- [ ] Did you cite the source file (`docs/raw/...`) and the markdown path (`docs/md/...`)?
- [ ] Did you flag any visual content limitations (images, charts, formulas)?
- [ ] If the document is long, did you use progressive reading (head -50, grep, line range)?

**For text-based documents (TXT, MD, HTML, CSV, JSON, XML):**
- [ ] Did you read the file directly (no pipeline overhead needed)?
- [ ] Did you cite the source file path?
- [ ] If the file is large, did you use progressive reading?
