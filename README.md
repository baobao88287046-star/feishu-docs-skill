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

## Verify

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py doctor --env .env
```

Read a Feishu Wiki or Docx link:

```bash
python3 ~/.codex/skills/feishu-docs/scripts/feishu_docs.py read-url 'https://xxx.feishu.cn/wiki/xxx' --env .env --format text
```

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

