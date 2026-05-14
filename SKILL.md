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
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py add-docx-board <docx_token> --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py board-nodes <whiteboard_token> --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py create-board-nodes <whiteboard_token> ./nodes.json --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py replace-docx-md <docx_token> ./document.md --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-prd --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-docx --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-media --env .env
```

`--env` is optional. The helper loads credentials in this order:

1. The explicit `--env` path.
2. `.env` in the current working directory.
3. `~/.codex/secrets/feishu-docs.env`.
4. `~/.feishu-codex.env`.
5. Already-exported shell environment variables.

For one-time local setup:

```bash
mkdir -p ~/.codex/secrets
chmod 700 ~/.codex/secrets
cp ./feishu-docs.env ~/.codex/secrets/feishu-docs.env
chmod 600 ~/.codex/secrets/feishu-docs.env
```

After that, new Codex threads can usually run without `--env`:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py doctor
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

If `~/.codex/secrets/feishu-docs.env` exists, `--env .env` is not required.

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

### Replace An Existing Wiki/Docx Document

When the user asks to write into an existing Feishu Wiki/Docx URL, prefer replacing the document body instead of appending manually:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py resolve-url 'https://xxx.feishu.cn/wiki/xxxx'
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py replace-docx-md <resolved_docx_token> ./document.md --table-mode text
```

`replace-docx-md` clears the existing Docx body, then writes Markdown blocks with read-back resume. If Feishu closes the connection after a successful write, the command re-reads the document's current block count and continues from the correct index, avoiding duplicate or out-of-order blocks.

Use `--chunk-size 3` to `5` for long documents; the default is conservative and reliable. Use `--table-mode text` for long documents or PRD-like documents with many tables/lists.

Use `append-docx-md` only when the user explicitly wants to preserve existing content and append after it. It appends at the current end of the document.

### Restore Flowcharts Into Feishu Boards

When the user asks to create or restore a flowchart in Feishu, choose the output mode with this policy:

- If the user provides a visual reference, such as an SVG, screenshot, image, PDF, exported diagram, or says "参考图 / 照着图 / 还原 / 复原" with a file or image available, ask once before creating the board: "要按图片 1:1 还原，还是转成简化版可编辑泳道图？"
- If the user already specifies either mode, follow that mode without asking.
- If the user only provides text, steps, roles, or a process description, do not ask. Default to the editable swimlane version.

Output modes:

- **1:1 restoration**: preserve the original visual design as closely as possible.
- **Editable swimlane version**: simplify the process into Feishu's native board table/swimlane component. This is the default for text-only flowchart generation.

For both routes, create or reuse a Docx Board block first:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py add-docx-board <docx_token>
```

The command returns `board_token`, which is the whiteboard token for Board APIs.

#### Route A: 1:1 Visual Restoration

Use this when the user wants the original SVG/diagram appearance preserved.

1. Convert SVG or diagram source to Feishu board OpenAPI nodes. If `whiteboard-cli` is available, prefer:

   ```bash
   whiteboard-cli -i ./diagram.svg -f svg -t openapi -o /tmp/diagram.nodes.json
   ```

2. Ensure the output is a JSON array of nodes or extract the nested `data.result.nodes` array.
3. Assign stable `z_index` values in array order.
4. Remove read-only/internal fields before posting: top-level `id`, `locked`, `children`, `parent_id`; `text.*_type`; `style.*_type`; connector `start_object` and `end_object`.
5. Upload with:

   ```bash
   python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py create-board-nodes <board_token> ./nodes.json
   ```

This route can produce many nodes. It is visually faithful but may be harder for humans to edit.

#### Route B: Editable Swimlane Version

Use this when the user wants a maintainable swimlane/process map rather than pixel-perfect restoration.

Feishu's board swimlane template is exposed through the Board API as a `type: "table"` node. The table's `table.meta.row_sizes`, `table.meta.col_sizes`, and `table.cells` define the swimlane grid. Flow blocks and connectors are ordinary board nodes referenced by `table.cells[].children`.

Important creation order:

1. Create all flow blocks/connectors first with `create-board-nodes`; keep the returned IDs.
2. Create the `table` node second.
3. Put the returned IDs into the relevant `table.cells[].children` arrays.

Do **not** rely on setting `parent_id` when creating flow blocks. Feishu may ignore it on create. The reliable relationship is the table cell's `children` list.

When iterating on a swimlane generated from a reference board, preserve the reference board's business logic first. Do not add, remove, or reorder process transitions just to make connector layout easier unless the user explicitly asks to change the process. For example, if the first acceptable version has the clearest process logic, reuse that process graph and only change connector implementation, spacing, labels, or colors.

Recommended table pattern for business flow swimlanes:

- Column 1: stage labels, e.g. `step1`, `step2`, `step3`.
- Remaining columns: actors or responsibility areas, e.g. `C 端`, `B 端`, `结果 / 复用`.
- Use wider columns for areas with more nodes; add a final result column when right-side content would otherwise overflow.
- Keep connectors direct and readable, but never so short that the arrowhead touches text or looks detached from the source/target block.

Connector rules for Feishu Board swimlanes:

- Prefer object-bound connectors over absolute coordinate connectors. Create shapes first, capture returned IDs, then create connectors with `connector.start.attached_object.id` and `connector.end.attached_object.id`.
- Do not use `snap_to: "auto"` for swimlane connectors. Feishu may route the connector to an unexpected edge and draw lines along table boundaries. Use explicit edges:
  - Horizontal forward flow: source `right` to target `left`.
  - Vertical forward flow: source `bottom` to target `top`.
  - Reverse/feedback flow: choose explicit `top`/`bottom`/`left`/`right` edges that route through open space; keep it dashed red.
- If creating connectors through OpenAPI, `attached_object` must include `snap_to` as one of `top`, `right`, `bottom`, or `left`. `snap_to: "auto"` is allowed by the API but should be avoided for swimlanes.
- Avoid using `specified_coordinate: true` for normal process connectors inside table swimlanes. It creates absolute-position lines that can appear detached from shapes after Feishu renders the board.
- Avoid cross-row or cross-cell `polyline` routes with manual `turning_points` unless the points have been verified visually in Feishu. Object-bound connectors with explicit `snap_to` edges are safer than coordinate polyline routes.
- For decision diamonds, every outgoing branch must be labeled with `是` or `否`. Use small editable text boxes or connector captions near the corresponding branch; do not rely on the diamond text alone.
- Prefer connector captions for `是`/`否` labels instead of separate floating text boxes. Use `connector.captions.data` with a short text object, set `connector.caption_position_type` to `0` (`OnLine`), and place it with `connector.caption_position` around `0.45` to `0.6` so the label sits on the branch line. Use separate text boxes only if Feishu rejects captions for that connector.
- Preserve semantic colors across iterations: blue for normal process blocks, yellow/orange for decision diamonds, red/pink for rejection or rework, green for final success, and orange for reuse/loop notes such as "新增账号：复用 step2-4".
- Do not downgrade semantic result blocks to ordinary blue blocks when simplifying a swimlane.

Swimlane geometry rules:

- Treat every table cell as a hard container. Before creating nodes, compute each cell's bounds from the table `x/y`, `row_sizes`, and `col_sizes`.
- Use a grid layout for editable swimlanes. Within the same row, align related process blocks and decision diamonds to the same `y` center; within the same column, align vertical handoff blocks to the same `x` center. Prefer consistent row baselines such as `step2_y`, `step3_y`, `step4_y` instead of ad hoc positions.
- If two vertically adjacent flow steps can share the same `x` center without connector crossings, text overlap, or boundary collision, align them vertically. This is especially important for the main handoff chain between the last node of one stage and the first node of the next stage.
- Use a safe inset of at least `32` from every cell border. Use `48` when a block has incoming or outgoing connectors near that border.
- Keep block centers away from table row/column dividers. A block center should not sit on or near a swimlane divider; keep at least `80` horizontal distance from vertical dividers and at least `56` vertical distance from horizontal dividers unless the block is a header/stage label.
- A process block must fully fit inside its cell: `block.x >= cell_left + inset`, `block.y >= cell_top + inset`, `block.x + block.width <= cell_right - inset`, and `block.y + block.height <= cell_bottom - inset`.
- Never center a block on a swimlane divider or table border. If a block would overlap a row/column line, enlarge the row/column or move the block inward.
- Prefer compact block widths instead of filling cell width. Use the shortest width that preserves readable text and connectors: `170-210` for short one-line Chinese labels, `200-240` for typical two-line Chinese labels, and `240-260` for long two-line labels with separators such as `/`. Only use `280+` when a label would clearly clip after line breaks.
- Do not make all normal process blocks the same width by default. Keep visual consistency by using width tiers (`short`, `normal`, `long`) rather than one oversized global width. For example, `进入待首联池` should be narrower than `兼职执行装修 / 主页 / 资料 / 内容包装`.
- Do not leave large empty horizontal padding inside rectangles. If a block's horizontal padding is visually larger than the text width on both sides, shrink the block before upload.
- For short labels such as `提交装修结果`, `兼职确认人设`, `进入待首联池`, prefer widths around `190-220`; for two-line labels like `兼职注册\n提交基础信息`, prefer `210-230` unless the rendered text clips.
- Prefer block heights around `60-78` for normal process blocks. Use taller blocks only when multi-line text would clip.
- Keep at least `56` vertical gap between stacked blocks and at least `80` horizontal gap between neighboring blocks. If a connector needs an arrowhead between blocks, reserve at least `60` clear line length between the two block edges.
- Keep repeated elements visually consistent without over-widening them: normal process blocks in the same lane may share height and style, but widths should follow label length tiers; decision diamonds in the same diagram should share width/height; rejection/rework blocks should share size and color.
- Draw connectors from block edge to block edge, not from center to center. Horizontal flow: source right-midpoint to target left-midpoint. Vertical flow: source bottom-midpoint to target top-midpoint.
- Connector endpoints should touch or slightly overlap the block border by `0-4` units so the line appears attached after Feishu renders arrowheads. Do not leave a visible gap.
- Keep arrowheads outside text areas. If the line would collide with a label, route it through whitespace or move the blocks apart.
- Use dashed red feedback lines only for reverse/rework paths. Route them on a separate track below or above normal flow, with at least `24` clearance from block text and borders.
- Keep feedback/rework connectors local. A dashed red connector should normally stay within the same table cell or the same actor column. Do not draw long dashed lines that cross multiple swimlane columns. If the rework target is in another column, prefer adding a local red rework block in the source cell or a short note such as "退回补充" / "反馈修改" rather than a cross-column dashed connector.
- A connector may cross a vertical divider only when it represents the main forward handoff between adjacent actor columns. It should not run along a divider, overlap a divider, or cross more than one vertical divider in a single segment. Split or reroute if a connector bounding box spans more than two adjacent content columns.
- For decision diamonds, reserve more width than rectangles and keep connectors on their left/right/top/bottom tips. Do not let a diamond touch a cell border.
- If a row or column cannot satisfy these spacing rules, enlarge the table dimensions or row/column size before creating nodes. Do not shrink blocks until text becomes cramped.

Before uploading an editable swimlane board, run a manual layout checklist against the JSON:

- Build a small layout map first: list each cell's `{left, top, right, bottom}`, each block's `{left, top, right, bottom, center_x, center_y}`, and each connector's start/end coordinates.
- No block crosses or touches a table border or swimlane divider.
- No text is clipped inside a block.
- Every connector endpoint lands on the intended block edge.
- Every decision branch has an inline connector label (`是`/`否`) when captions are supported.
- No block center is near a swimlane divider, and no connector segment runs along a divider.
- No feedback/rework dashed connector crosses multiple columns; use local rework blocks instead.
- Every visible connector segment is long enough to show a clean arrowhead.
- No connector overlaps important text or cuts through a process block unless it is intentionally attached to that block.
- The rightmost and bottommost blocks still have safe padding inside the table.
- If any check fails, fix the JSON layout before calling `create-board-nodes`; do not rely on manual cleanup in Feishu.

Minimal table node shape:

```json
{
  "type": "table",
  "x": 60,
  "y": 60,
  "width": 1450,
  "height": 880,
  "z_index": 0,
  "style": {
    "border_color": "#000000",
    "border_opacity": 100,
    "border_style": "solid",
    "border_width": "narrow",
    "fill_opacity": 100
  },
  "table": {
    "title": "",
    "meta": {
      "row_num": 5,
      "col_num": 4,
      "row_sizes": [70, 170, 220, 210, 210],
      "col_sizes": [150, 470, 470, 360],
      "style": {
        "border_color": "#000000",
        "border_opacity": 100,
        "border_style": "solid",
        "border_width": "extra_narrow",
        "fill_opacity": 100
      },
      "text": {
        "text": "",
        "font_size": 14,
        "font_weight": "regular",
        "horizontal_align": "left",
        "vertical_align": "top",
        "text_color": "#1f2329"
      }
    },
    "cells": [
      {"row_index": 1, "col_index": 1, "text": {"text": "阶段", "font_size": 18, "font_weight": "bold", "horizontal_align": "center", "vertical_align": "mid", "text_color": "#1f2329"}, "style": {"fill_color": "#f5f5f5", "fill_opacity": 100}},
      {"row_index": 2, "col_index": 2, "children": ["o1:1", "c1:1"], "style": {"fill_opacity": 100}}
    ]
  }
}
```

For best maintainability, keep the swimlane version simpler than the 1:1 version: fewer nodes, larger blocks, and concise labels.

## Bitable Notes

This version supports credential checks, URL resolution, Docx reads, Docx Markdown-subset appends, PRD Markdown publishing, Docx roundtrip validation, and table/image insertion validation. For Bitable writes, use the helper's token acquisition and resolved `app_token`, then call Feishu's Bitable endpoints according to the target table/field schema.

## Reliability Guidance

- Native Feishu tables are supported and validated by `roundtrip-media`, but they require many per-cell write requests. For long documents or documents with many tables, use automatic or text table mode to avoid connection drops or accidental duplicate cells.
- For replacing existing Docx content, use `replace-docx-md`; it is designed for network disconnects and resumes from the actual block count after each failure.
- Non-idempotent append/create requests are not automatically retried. If a manual append fails due to a network disconnect, inspect the partial document before continuing.
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
