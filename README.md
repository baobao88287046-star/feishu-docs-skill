# feishu-docs Codex Skill

Codex skill for reading and troubleshooting Feishu/Lark Wiki, cloud documents, Docx, Sheets, and Bitable/Base links.

This repository contains no Feishu secrets. Each user must configure their own local `.env` file.

## Install

Clone this private repository, then copy it into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
git clone git@github.com:baobao88287046-star/feishu-docs-skill.git /tmp/feishu-docs-skill
rm -rf ~/.codex/skills/feishu-docs
cp -R /tmp/feishu-docs-skill ~/.codex/skills/feishu-docs
```

Restart Codex after installing the skill.

## Configure

Create a local `.env` file in the project where you use Codex:

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_app_secret
```

Do not commit `.env`.

For new Codex threads to work without passing `--env` every time, put the same values in a local private global file:

```bash
mkdir -p ~/.codex/secrets
chmod 700 ~/.codex/secrets
cp ./feishu-docs.env ~/.codex/secrets/feishu-docs.env
chmod 600 ~/.codex/secrets/feishu-docs.env
```

Credential lookup order:

```text
explicit --env path
current directory .env
~/.codex/secrets/feishu-docs.env
~/.feishu-codex.env
exported environment variables
```

## Verify

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py doctor --env .env
```

If global credentials are configured:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py doctor
```

Read a Feishu Wiki or Docx link:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py read-url 'https://xxx.feishu.cn/wiki/xxx' --env .env --format text
```

Append an empty editable board to a Docx:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py add-docx-board <docx_token> --env .env
```

Read and write Feishu board nodes:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py board-nodes <whiteboard_token> --env .env
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py create-board-nodes <whiteboard_token> ./nodes.json --env .env
```

Validate long Docx writing:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-docx --env .env --sections 20 --paragraphs-per-section 5 --chunk-size 12 --output-dir /tmp/feishu-docs-roundtrip
```

The validation command creates a test document, writes generated Markdown content in chunks, reads it back, and diffs expected vs. actual normalized text. A healthy run reports:

```json
{
  "matched": true
}
```

Validate table and image insertion:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-media --env .env
```

With a real image:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-media --env .env --image ./example.png
```

The media validation command creates a test document, inserts a table, fills table cells, inserts an image block, uploads image media, binds it to the block, reads the document back, and verifies both table and image structure.

## Markdown Document Publishing

Create a Feishu Docx from Markdown:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env
```

The default `--table-mode auto` chooses table handling from the document content. Small/few tables use native Feishu tables. Many or large tables use stable aligned text rows.

Validate the document-writing path:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py roundtrip-prd --env .env
```

Force native Feishu table cells:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env --table-mode native
```

Force stable text tables:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py write-doc-md ./document.md --env .env --table-mode text
```

`write-prd-md` remains available as a compatibility alias, but the recommended entry point is `write-doc-md`.

## Flowchart Board Restoration

The skill supports two board-restoration patterns:

- If a visual reference is available, such as an SVG, screenshot, image, PDF, or exported diagram, ask whether to create a **1:1 restoration** or an **editable swimlane version** unless the user already chose one.
- If the user only provides text, steps, roles, or a process description, default to the **editable swimlane version** without asking.

- **1:1 restoration**: convert SVG/diagram source to Feishu board OpenAPI nodes, usually through `whiteboard-cli -t openapi`, then upload with `create-board-nodes`.
- **Editable swimlane version**: use Feishu board `table` nodes as the swimlane carrier. Create flow blocks/connectors first, then create the `table` node with `table.cells[].children` referencing the returned node IDs.

Important: setting `parent_id` on flow nodes is not enough to attach them to the table. The reliable template-style swimlane relationship is stored in `table.cells[].children`.

For editable swimlanes, compute cell bounds before creating nodes. Keep process blocks fully inside cells with at least `32` padding from borders and dividers, use larger rows/columns instead of cramped labels, and draw connectors edge-to-edge with clear arrowhead space. Before upload, map every cell bounds, block bounding box, and connector endpoint. Do not upload a board JSON if connectors float near blocks, cross text, or if blocks touch table boundaries.

## Feishu Requirements

The enterprise app must have the required API scopes and the target document must add the app as a document app/collaborator.

See:

```text
references/permissions.md
```

## Typical Codex Prompt

```text
Use $feishu-docs to read this Feishu document link and summarize it: https://...
```
