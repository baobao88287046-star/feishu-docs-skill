# Feishu Permissions Reference

Use this reference when Feishu API calls fail with permission errors or when setting up a new enterprise app for Codex/CLI access.

## App Console

Open:

```text
https://open.feishu.cn/app
```

In the target enterprise self-built app, use:

```text
开发配置 -> 权限管理
```

After adding scopes, publish a new version:

```text
版本管理与发布 -> 创建版本 -> 发布/审批
```

## Minimal Scopes

Read Wiki links that point to Docx:

```text
wiki:node:read
docx:document:readonly
```

Read and write Docx:

```text
wiki:node:read
docx:document
```

Read and write Docx Board/whiteboard nodes:

```text
wiki:node:read
docx:document
board:whiteboard:node:read
board:whiteboard:node:create
```

Add update/delete only when modifying or clearing existing board nodes:

```text
board:whiteboard:node:update
board:whiteboard:node:delete
```

Read cloud file metadata:

```text
drive:drive:readonly
```

Read and write cloud files:

```text
drive:drive
```

Read Sheets:

```text
sheets:spreadsheet:readonly
```

Read and write Sheets:

```text
sheets:spreadsheet
```

Read and write Bitable/Base records:

```text
wiki:node:read
bitable:app
base:app:read
base:record:retrieve
base:record:create
base:record:update
base:table:read
base:field:read
base:view:read
```

Only add delete permission when needed:

```text
base:record:delete
```

## Document-Level Authorization

API scopes are not enough. The specific target document, Wiki page, Sheet, or Bitable must also authorize the enterprise app.

In the document UI:

```text
分享/更多 -> 添加文档应用 -> 选择应用 -> 授予可阅读或可编辑
```

If an app can resolve a Wiki node but cannot read the backing document, check Docx/Sheets/Bitable scopes and document-level authorization.

## Common Errors

### 99991672 Missing Scope

Example:

```json
{
  "code": 99991672,
  "msg": "Access denied. One of the following scopes is required: [wiki:wiki, wiki:wiki:readonly, wiki:node:read]"
}
```

Fix:

1. Add one of the listed scopes.
2. Publish a new app version.
3. Fetch a new `tenant_access_token`.
4. Retry.

### Token Works, Document Read Fails

Likely causes:

- Missing API scope for the backing object type.
- App version not published after adding scopes.
- The specific document did not add the app as collaborator/document app.
- The URL is a Wiki node and was not resolved to `obj_token`.
