# Document Reading Policy

Claude Code 在处理项目文档时必须遵守以下规则，确保稳定、一致、可重现的文档分析流程。

---

## 核心原则

**绝不直接读取二进制文档。** 所有原始文档（PDF、DOCX、PPTX、XLSX、图片、音频等）必须通过 MarkItDown 转换为 Markdown 后，方可进行文本分析。

---

## 规则

### A. 禁止直接读取原始文件

不得直接读取 `docs/raw/` 下的任何文件。这些文件是二进制格式或非纯文本格式，直接读取会导致乱码、内容丢失或不准确的分析。

### B. 优先查看索引

需要文档内容时，首先查看 `docs/index.jsonl`。索引文件每行是一个 JSON 对象，包含：

| 字段 | 说明 |
|------|------|
| `source_path` | 源文件相对路径 |
| `source_filename` | 源文件名 |
| `source_ext` | 文件扩展名 |
| `sha256` | 源文件的 SHA256 哈希 |
| `markdown_path` | 转换后的 Markdown 文件路径 |
| `metadata_path` | Metadata JSON 路径 |
| `converted_at` | 转换时间 (UTC ISO 8601) |
| `status` | 状态: SUCCESS / FAILED / SKIPPED |
| `warnings` | 质量警告列表 |

### C. 只读取 Markdown

找到对应文档后，只读取 `docs/md/` 下的 `.md` 文件。不要读取 `docs/meta/` 中的 metadata JSON 来获取内容。

### D. 自动转换缺失文档

如果 `docs/index.jsonl` 中有记录但 Markdown 文件不存在，运行：

```bash
python scripts/ingest_document.py <source_path>
```

如果 Markdown 文件和索引都不存在，同样先运行 ingest 脚本。

### E. 分块读取长文档

Markdown 文件过长时，按以下策略分块读取：

1. 先用 `head -n 100` 或读取前 100 行获取大纲
2. 根据标题（`# `, `## `）定位到目标章节
3. 使用行偏移（offset/limit）分块读取
4. 必要时按关键词搜索定位

### F. 标注局限性

对以下类型的内容，必须在回答中标注**"可能需要视觉模型或人工复核"**：

- 图片 / 扫描 PDF
- 复杂表格（多行列合并、嵌套表）
- 数学公式（LaTeX 渲染结果）
- 图表 / 流程图 / 架构图
- OCR 提取的文本

### G. 禁止臆造内容

MarkItDown 没有提取出来的内容，不得凭推测补全。如果 Markdown 中缺少预期内容，应说明"该内容未被 MarkItDown 提取"。

### H. 引用来源

所有回答必须引用：

- 源文件名：`docs/raw/<filename>`
- Markdown 路径：`docs/md/<filename>`
- 如有必要，引用 metadata 中的警告信息

### I. 处理转换失败

对于状态为 `FAILED` 的文档：

1. 查看 `docs/meta/` 中对应 metadata JSON 的 `error_message` 字段
2. 根据错误信息给出修复建议（缺少依赖、文件损坏、加密等）
3. 不要尝试读取可能不完整或损坏的 Markdown 文件

---

## 工作流程示例

```
需求：分析一份 PDF 论文
1. 检查 docs/index.jsonl 是否存在该论文记录
2. 如果不存在 → 运行 python scripts/ingest_document.py docs/raw/paper.pdf
3. 如果存在但状态为 FAILED → 查看 docs/meta/ 中的错误信息
4. 如果状态为 SUCCESS → 读取 docs/md/paper.abc123def456.md
5. 如果文件过长 → 先读前 100 行，定位章节，再针对性读取
6. 涉及图表 → 标注"可能需要视觉模型或人工复核"
```

---

## 缓存清理

如果 Markdown 文件损坏或需要重新转换：

```bash
python scripts/clean_document_cache.py --path docs/raw/<file>  # 清除单个
python scripts/clean_document_cache.py --status FAILED          # 清除所有失败
python scripts/clean_document_cache.py --stale                  # 清除源文件已不存在的记录
```

然后重新运行 `scripts/ingest_document.py`。
