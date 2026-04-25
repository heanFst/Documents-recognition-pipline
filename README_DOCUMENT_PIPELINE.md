# Document Markdown Pipeline

基于 Microsoft MarkItDown 的文档识别与 Markdown 化标准流程。

## 目录结构

```
project/
├── docs/
│   ├── raw/             原始文档（只存放源文件）
│   ├── md/              转换后的 Markdown
│   ├── meta/            每个文档的 metadata JSON
│   ├── assets/          图片、附件、后处理资源
│   ├── failed/          转换失败的文件副本
│   └── index.jsonl      全量文档索引（JSONL 格式）
├── scripts/
│   ├── ingest_document.py     文档转换入口
│   ├── inspect_document.py    文档索引查看
│   └── clean_document_cache.py 缓存清理
└── .claude/
    └── document_policy.md     Claude Code 文档读取规则
```

## 安装

```bash
# 创建虚拟环境（Python 3.10+）
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (Git Bash / WSL)
source .venv/Scripts/activate

# 安装 MarkItDown（含所有可选依赖）
pip install 'markitdown[all]'
```

## 基本使用

### 转换单个文件

```bash
python scripts/ingest_document.py docs/raw/paper.pdf
```

### 批量转换目录

```bash
# 仅当前目录
python scripts/ingest_document.py docs/raw/

# 递归扫描所有子目录
python scripts/ingest_document.py docs/raw/ --recursive
```

### 强制重新转换

SHA256 未变化时默认跳过。需要强制重转：

```bash
python scripts/ingest_document.py docs/raw/paper.pdf --force
```

### 预览模式（不执行转换）

```bash
python scripts/ingest_document.py docs/raw/paper.pdf --dry-run
```

## 输出文件命名

- 原始文件名去扩展名 + 前 12 位 SHA256 + `.md`
- 例：`paper.pdf` → `paper.a1b2c3d4e5f6.md`
- 同上，metadata 为 `.json`：`paper.a1b2c3d4e5f6.json`

## 索引查看

```bash
# 列出所有文档
python scripts/inspect_document.py

# 按状态筛选
python scripts/inspect_document.py --status FAILED
python scripts/inspect_document.py --status SUCCESS

# 搜索文件名
python scripts/inspect_document.py --search paper

# 按 hash 前缀搜索
python scripts/inspect_document.py --hash a1b2c3d4e5f6

# 查看单个文档
python scripts/inspect_document.py --path docs/raw/paper.pdf

# 查看统计信息
python scripts/inspect_document.py --stats

# 查看完整 metadata JSON
python scripts/inspect_document.py --verbose
```

## 缓存清理

```bash
# 预览将要删除的文件
python scripts/clean_document_cache.py --dry-run

# 清除所有转换结果
python scripts/clean_document_cache.py

# 清除所有失败记录
python scripts/clean_document_cache.py --status FAILED

# 清除源文件已不存在的记录
python scripts/clean_document_cache.py --stale

# 清除特定文档
python scripts/clean_document_cache.py --path docs/raw/paper.pdf

# 跳过确认
python scripts/clean_document_cache.py --yes
```

## 支持的格式

| 类别 | 格式 |
|------|------|
| 文档 | PDF, DOCX, PPTX, XLSX, XLS, CSV, EPUB |
| 网页 | HTML, HTM, XML, JSON |
| 文本 | TXT, MD |
| 图片 | PNG, JPG, JPEG, WebP, GIF |
| 音频 | MP3, WAV |
| 压缩包 | ZIP |

## Claude Code 集成

Claude Code 应遵循 `.claude/document_policy.md` 中定义的规则处理文档。核心要点：

1. 不直接读取 `docs/raw/` 下的二进制文件
2. 优先查看 `docs/index.jsonl` 获取文档索引
3. 只读取 `docs/md/` 下的 Markdown 文件
4. 长文件按标题/段落分块读取
5. Markdown 不存在时先运行 ingest 脚本
6. 对图片、扫描件、图表标注"可能需要视觉模型或人工复核"
7. 引用来源时注明文件名和 Markdown 路径

## 常见失败原因

| 原因 | 表现 | 解决方案 |
|------|------|----------|
| 缺少可选依赖 | CLI/API 报 ImportError | `pip install 'markitdown[all]'` |
| PDF 是扫描件 | 输出为空或很少文本 | 需要 OCR（Azure Document Intelligence 或 Tesseract） |
| 文件损坏 | MarkItDown 解析失败 | 检查源文件完整性 |
| 加密 PDF | 无法打开 | 先解密 |
| 超大 Excel | 超时或 OOM | 拆分文件或仅转换部分 sheet |
| 图片 OCR 质量差 | 文本乱码或缺失 | 使用更高精度 OCR 引擎 |
| 第三方 API 不支持视觉 | 图片输出为空 | 使用本地 OCR 或手动转录 |

## 推荐策略

| 文档类型 | 策略 |
|----------|------|
| 普通文本 PDF / Word / PPT / Excel | 直接 MarkItDown |
| 扫描 PDF | MarkItDown 失败或文本过少 → 标记 `OCR_REQUIRED` |
| 图片 | 保留 OCR 结果和 EXIF 信息 |
| 表格 | 保留 Markdown 表格，必要时导出为 CSV |
| 公式和图表 | 提取结果必须人工复核 |

## 质量保证

转换完成后自动执行以下检查：

- **LOW_TEXT_EXTRACTION**: Markdown 字符数 < 100 且源文件 > 100KB
- **POSSIBLE_ENCODING_OR_OCR_ERROR**: 乱码字符比例超过 5%
- **WEAK_STRUCTURE**: PDF/PPTX/DOCX 转换后缺少标题层级
- **FAILED**: Markdown 文件不存在或为空

所有警告和错误被记录到 metadata JSON 和 `docs/index.jsonl`。
