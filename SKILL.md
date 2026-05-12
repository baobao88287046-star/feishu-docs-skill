---
name: feishu-docs
description: Use when reading, writing, validating, or troubleshooting Feishu/Lark Wiki, cloud documents, Docx, Sheets, or Bitable/Base links from Codex or a local CLI. Handles Feishu enterprise app credentials, tenant_access_token, wiki node resolution, docx block reads, Bitable record operations, and permission diagnostics.
---

# Feishu Docs

Use this skill for Feishu/Lark document work from Codex: reading Wiki links, cloud documents, Docx blocks, Sheets, or Bitable/Base records; validating enterprise app credentials; and diagnosing missing permissions.

Never hard-code `App Secret` in skill files or generated code. Read credentials from environment variables or a local env file that the user controls.

## Quick Start

Use the bundled helper for repeatable API calls:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py doctor --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py resolve-url 'https://xxx.feishu.cn/wiki/...' --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py read-url 'https://xxx.feishu.cn/wiki/...' --env .env --format text
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-prd --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-docx --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-media --env .env
```

Credential env names accepted by the helper:

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

Fallback names are also accepted:

```bash
LARK_APP_ID=cli_xxx
LARK_APP_SECRET=xxx
APP_ID=cli_xxx
APP_SECRET=xxx
```

## Workflow

1. If credentials may be missing or stale, run `doctor`.
2. Parse the user-provided Feishu URL.
3. For `/wiki/` URLs, call `resolve-url` first. Wiki URLs contain a node token, not the final document token.
4. Dispatch by resolved type:
   - `docx`: read blocks with `read-url` or call Docx APIs directly.
   - `sheet`: use Sheets APIs.
   - `bitable` or `base`: use Bitable/Base APIs.
5. If a permission error appears, read `references/permissions.md` for the minimal scope and publish steps.

## URL Rules

- `/wiki/{node_token}`: resolve with `wiki/v2/spaces/get_node`, then use `obj_type` and `obj_token`.
- `/docx/{document_token}`: use Docx APIs directly.
- `/base/{app_token}` or `/bitable/{app_token}`: use Bitable/Base APIs directly.
- `/sheets/{spreadsheet_token}`: use Sheets APIs directly.

## Common Tasks

### Validate Credentials

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py doctor --env .env
```

Successful output includes `code: 0`, token expiry, and a masked token.

### Read a Wiki or Docx Link

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py read-url 'https://xxx.feishu.cn/wiki/xxxx' --env .env --format text
```

For Wiki links, the helper resolves the node before reading the backing object.

### Inspect Raw API Data

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py read-url 'https://xxx.feishu.cn/docx/xxxx' --env .env --format json --page-size 20
```

Use JSON when preserving block IDs or formatting details matters.

### Validate Long Docx Writes

Use `roundtrip-docx` before trusting long-document generation. It creates a test Docx, writes generated or provided Markdown in chunks, reads the document back, normalizes text, and diffs expected vs. actual output.

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-docx --env .env --sections 20 --paragraphs-per-section 5 --chunk-size 12 --output-dir /tmp/feishu-docs-roundtrip
```

The command should report `matched: true`. If it fails, inspect `expected.txt`, `actual.txt`, and `source.md` in the output directory.

For a custom fixture:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-docx --env .env --markdown tests/fixtures/long_doc.md --output-dir /tmp/feishu-docs-roundtrip
```

### Validate Tables And Images

Use `roundtrip-media` to test the fragile media chain: create table block, write table cells, create image block, upload image media, bind image token, read back, and validate structure.

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-media --env .env
```

With a real local image:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-media --env .env --image ./example.png
```

The command should report `matched: true`, with both `table.validated` and `image.validated` set to `true`.

### Write Markdown Documents

Use `write-doc-md` for real Markdown document publishing. It supports headings, paragraphs, ordered/unordered lists, task-list text, Markdown tables, local images, quote text, and fenced code as plain text.

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env
```

The default `--table-mode auto` inspects document content:

- Small/few tables use native Feishu tables.
- Many or large tables use aligned text rows because they are much more reliable for long documents.

To force native Feishu tables:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env --table-mode native
```

To force stable text tables:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env --table-mode text
```

`write-prd-md` remains as a compatibility alias, but do not treat PRD as a special case. Choose behavior from the document content and user needs.

## Bitable Notes

This version supports credential checks, URL resolution, Docx reads, Docx Markdown-subset appends, PRD Markdown publishing, Docx roundtrip validation, and table/image insertion validation. For Bitable writes, use the helper's token acquisition and resolved `app_token`, then call Feishu's Bitable endpoints according to the target table/field schema.

## Reliability Guidance

- Native Feishu tables are supported and validated by `roundtrip-media`, but they require many per-cell write requests. For long documents or documents with many tables, use automatic or text table mode to avoid connection drops or accidental duplicate cells.
- Non-idempotent write requests are not automatically retried. If a write fails due to a network disconnect, rerun into a fresh test document and inspect the partial document if needed.
- Quote blocks and code blocks are written as plain text for stability.
- Local image paths in Markdown, such as `![diagram](./diagram.png)`, are uploaded and inserted into the document. Remote image URLs are not downloaded automatically yet.

When implementing Bitable writes:

- Ask for or inspect `table_id`.
- Fetch fields before writing so field names and types are known.
- Prefer updates by stable record IDs or a clearly unique key.
- Do not delete records unless the user explicitly asks.

## Troubleshooting

For missing scopes, app publishing, and document collaborator setup, read:

```text
~/.codex/skills/feishu-docs/references/permissions.md
```

High-signal checks:

- API scopes must be added in the Feishu app console.
- After changing scopes, create and publish a new app version.
- The target document or Bitable must add the enterprise app as a document app/collaborator.
- Re-fetch `tenant_access_token` after permission changes.
