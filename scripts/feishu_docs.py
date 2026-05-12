#!/usr/bin/env python3
"""Small Feishu/Lark document helper for Codex skills.

The script intentionally avoids external dependencies. It reads credentials from
environment variables or a simple KEY=VALUE env file.
"""

from __future__ import annotations

import argparse
import difflib
import base64
import json
import mimetypes
import os
import re
import sys
import tempfile
import time
import http.client
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple


API_BASE = "https://open.feishu.cn/open-apis"


class FeishuError(RuntimeError):
    pass


def load_env_file(path: Optional[str]) -> None:
    if not path:
        return
    if not os.path.exists(path):
        raise FeishuError(f"env file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def first_env(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def credentials() -> Tuple[str, str]:
    app_id = first_env(["FEISHU_APP_ID", "LARK_APP_ID", "APP_ID"])
    app_secret = first_env(["FEISHU_APP_SECRET", "LARK_APP_SECRET", "APP_SECRET"])
    if not app_id or not app_secret:
        raise FeishuError(
            "missing credentials; set FEISHU_APP_ID and FEISHU_APP_SECRET "
            "(or LARK_APP_ID/LARK_APP_SECRET)"
        )
    return app_id, app_secret


def request_json(
    method: str,
    path_or_url: str,
    token: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = path_or_url if path_or_url.startswith("http") else API_BASE + path_or_url
    if query:
        encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        url = url + ("&" if "?" in url else "?") + encoded

    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    payload = ""
    method_upper = method.upper()
    # Avoid retrying non-idempotent writes. If a create-child request succeeds
    # server-side but the connection drops, retrying can duplicate document blocks.
    max_attempts = 3 if method_upper == "GET" or path_or_url.endswith("/tenant_access_token/internal") else 1
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method_upper)
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = resp.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                time.sleep(1.5 * attempt)
                continue
            raise FeishuError(f"HTTP {exc.code}: {payload}") from exc
        except (urllib.error.URLError, http.client.RemoteDisconnected) as exc:
            if attempt < max_attempts:
                time.sleep(1.5 * attempt)
                continue
            raise FeishuError(f"network error: {exc}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FeishuError(f"non-json response: {payload[:500]}") from exc


def request_multipart_json(
    path_or_url: str,
    token: str,
    fields: Dict[str, Any],
    file_field: str,
    file_path: str,
) -> Dict[str, Any]:
    url = path_or_url if path_or_url.startswith("http") else API_BASE + path_or_url
    boundary = "----feishuDocsBoundary" + str(int(time.time() * 1000))
    file_name = os.path.basename(file_path)
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    with open(file_path, "rb") as fh:
        file_bytes = fh.read()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise FeishuError(f"HTTP {exc.code}: {payload}") from exc
    except urllib.error.URLError as exc:
        raise FeishuError(f"network error: {exc}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FeishuError(f"non-json response: {payload[:500]}") from exc


def tenant_access_token() -> Dict[str, Any]:
    app_id, app_secret = credentials()
    return request_json(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        body={"app_id": app_id, "app_secret": app_secret},
    )


def get_token_or_raise() -> str:
    data = tenant_access_token()
    if data.get("code") != 0:
        raise FeishuError(json.dumps(data, ensure_ascii=False, indent=2))
    token = data.get("tenant_access_token")
    if not token:
        raise FeishuError("tenant_access_token missing in response")
    return token


def mask_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return token
    if len(token) <= 14:
        return token[:3] + "..."
    return token[:8] + "..." + token[-6:]


def parse_feishu_url(url: str) -> Dict[str, str]:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) < 2:
        raise FeishuError(f"cannot parse Feishu URL path: {path}")

    kind = parts[0]
    token = parts[1]
    if kind == "wiki":
        return {"kind": "wiki", "token": token}
    if kind == "docx":
        return {"kind": "docx", "token": token, "obj_type": "docx", "obj_token": token}
    if kind in ("base", "bitable"):
        return {"kind": "bitable", "token": token, "obj_type": "bitable", "obj_token": token}
    if kind in ("sheets", "sheet"):
        return {"kind": "sheet", "token": token, "obj_type": "sheet", "obj_token": token}
    raise FeishuError(f"unsupported Feishu URL kind: {kind}")


def resolve_url(url: str, token: str) -> Dict[str, Any]:
    parsed = parse_feishu_url(url)
    if parsed["kind"] != "wiki":
        return {"code": 0, "msg": "direct_url", "data": {"node": parsed}}
    return request_json(
        "GET",
        "/wiki/v2/spaces/get_node",
        token=token,
        query={"token": parsed["token"]},
    )


def docx_blocks(docx_token: str, token: str, page_size: int = 50, page_token: Optional[str] = None) -> Dict[str, Any]:
    return request_json(
        "GET",
        f"/docx/v1/documents/{docx_token}/blocks",
        token=token,
        query={"page_size": page_size, "page_token": page_token},
    )


def create_docx(title: str, token: str, folder_token: Optional[str] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"title": title}
    if folder_token:
        body["folder_token"] = folder_token
    return request_json("POST", "/docx/v1/documents", token=token, body=body)


def create_docx_children(
    docx_token: str,
    parent_block_id: str,
    token: str,
    children: List[Dict[str, Any]],
    index: int,
) -> Dict[str, Any]:
    return request_json(
        "POST",
        f"/docx/v1/documents/{docx_token}/blocks/{parent_block_id}/children",
        token=token,
        query={"document_revision_id": -1},
        body={"children": children, "index": index},
    )


def patch_docx_block(docx_token: str, block_id: str, token: str, body: Dict[str, Any]) -> Dict[str, Any]:
    return request_json(
        "PATCH",
        f"/docx/v1/documents/{docx_token}/blocks/{block_id}",
        token=token,
        query={"document_revision_id": -1},
        body=body,
    )


def upload_docx_image(docx_token: str, image_block_id: str, token: str, image_path: str) -> Dict[str, Any]:
    size = os.path.getsize(image_path)
    return request_multipart_json(
        "/drive/v1/medias/upload_all",
        token=token,
        fields={
            "file_name": os.path.basename(image_path),
            "parent_type": "docx_image",
            "parent_node": image_block_id,
            "size": size,
        },
        file_field="file",
        file_path=image_path,
    )


def extract_created_children(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = response.get("data", {})
    children = data.get("children")
    if isinstance(children, list):
        return children
    block = data.get("block")
    if isinstance(block, dict):
        return [block]
    return []


def extract_file_token(response: Dict[str, Any]) -> str:
    data = response.get("data", {})
    token = data.get("file_token") or data.get("token")
    if token:
        return token
    file_data = data.get("file")
    if isinstance(file_data, dict):
        token = file_data.get("file_token") or file_data.get("token")
        if token:
            return token
    raise FeishuError(f"cannot find file token in response: {json.dumps(response, ensure_ascii=False)}")


def create_table_with_values(
    docx_token: str,
    token: str,
    values: List[List[str]],
    index: int = -1,
) -> Dict[str, Any]:
    row_size = len(values)
    column_size = max((len(row) for row in values), default=0)
    table_block = {
        "block_type": 31,
        "table": {
            "property": {
                "row_size": row_size,
                "column_size": column_size,
                "header_row": True,
            }
        },
    }
    response = create_docx_children(docx_token, docx_token, token, [table_block], index=index)
    if response.get("code") != 0:
        raise FeishuError(json.dumps(response, ensure_ascii=False, indent=2))
    children = extract_created_children(response)
    if not children:
        raise FeishuError(f"table create response did not include children: {json.dumps(response, ensure_ascii=False)}")
    table = children[0]
    table_id = table.get("block_id")
    cells = table.get("table", {}).get("cells", [])
    if not table_id or len(cells) < row_size * column_size:
        raise FeishuError(f"table response missing cells: {json.dumps(response, ensure_ascii=False)}")
    flat_values: List[str] = []
    for row in values:
        padded = list(row) + [""] * (column_size - len(row))
        flat_values.extend(padded)
    for idx, (cell_id, content) in enumerate(zip(cells, flat_values)):
        cell_block = text_block("text", 2, content)
        # Bold header row for a stronger readback signal.
        if idx < column_size:
            cell_block["text"]["elements"][0]["text_run"]["text_element_style"]["bold"] = True
        data = create_docx_children(docx_token, cell_id, token, [cell_block], index=0)
        if data.get("code") != 0:
            raise FeishuError(json.dumps(data, ensure_ascii=False, indent=2))
        time.sleep(0.12)
        if idx and idx % 8 == 0:
            time.sleep(0.6)
    return {"table_id": table_id, "cells": cells, "values": values}


def create_image_block_with_file(
    docx_token: str,
    token: str,
    image_path: str,
    index: int = -1,
) -> Dict[str, Any]:
    response = create_docx_children(docx_token, docx_token, token, [{"block_type": 27, "image": {}}], index=index)
    if response.get("code") != 0:
        raise FeishuError(json.dumps(response, ensure_ascii=False, indent=2))
    children = extract_created_children(response)
    if not children:
        raise FeishuError(f"image block create response did not include children: {json.dumps(response, ensure_ascii=False)}")
    image_block_id = children[0].get("block_id")
    if not image_block_id:
        raise FeishuError(f"image block id missing: {json.dumps(response, ensure_ascii=False)}")
    upload_response = upload_docx_image(docx_token, image_block_id, token, image_path)
    if upload_response.get("code") != 0:
        raise FeishuError(json.dumps(upload_response, ensure_ascii=False, indent=2))
    file_token = extract_file_token(upload_response)
    patch_response = patch_docx_block(docx_token, image_block_id, token, {"replace_image": {"token": file_token}})
    if patch_response.get("code") != 0:
        raise FeishuError(json.dumps(patch_response, ensure_ascii=False, indent=2))
    return {"image_block_id": image_block_id, "file_token": file_token}


def write_sample_png(path: str) -> None:
    # 1x1 PNG, enough to validate Feishu's image upload/bind flow.
    png_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(png_base64))


def all_docx_blocks(docx_token: str, token: str, page_size: int = 100) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        data = docx_blocks(docx_token, token, page_size=page_size, page_token=page_token)
        if data.get("code") != 0:
            raise FeishuError(json.dumps(data, ensure_ascii=False, indent=2))
        chunk = data.get("data", {}).get("items", [])
        items.extend(chunk)
        if not data.get("data", {}).get("has_more"):
            break
        page_token = data.get("data", {}).get("page_token")
        if not page_token:
            break
        time.sleep(0.25)
    return items


def text_element(content: str) -> Dict[str, Any]:
    return {
        "text_run": {
            "content": content,
            "text_element_style": {
                "bold": False,
                "italic": False,
                "strikethrough": False,
                "underline": False,
                "inline_code": False,
            },
        }
    }


def text_block(block_key: str, block_type: int, content: str) -> Dict[str, Any]:
    return {
        "block_type": block_type,
        block_key: {
            "elements": [text_element(content)],
            "style": {"align": 1, "folded": False},
        },
    }


def markdown_to_docx_blocks(markdown: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    in_code = False
    code_lines: List[str] = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            blocks.append(text_block("text", 2, "\n".join(code_lines)))
            code_lines = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
                code_lines = []
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            continue
        if stripped.startswith("### "):
            blocks.append(text_block("heading3", 5, stripped[4:]))
        elif stripped.startswith("## "):
            blocks.append(text_block("heading2", 4, stripped[3:]))
        elif stripped.startswith("# "):
            blocks.append(text_block("heading1", 3, stripped[2:]))
        elif stripped.startswith("- "):
            blocks.append(text_block("bullet", 12, stripped[2:]))
        elif re.match(r"^\d+\.\s+", stripped):
            blocks.append(text_block("ordered", 13, re.sub(r"^\d+\.\s+", "", stripped)))
        elif stripped.startswith("> "):
            blocks.append(text_block("text", 2, f"引用：{stripped[2:]}"))
        else:
            blocks.append(text_block("text", 2, stripped))
    if in_code:
        flush_code()
    return blocks


def is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(re.match(r"^:?-{3,}:?$", cell or "") for cell in cells)


def parse_markdown_table(lines: List[str], start: int) -> Optional[Tuple[List[List[str]], int]]:
    if start + 1 >= len(lines):
        return None
    header = lines[start].strip()
    separator = lines[start + 1].strip()
    if "|" not in header or not is_markdown_table_separator(separator):
        return None
    rows: List[List[str]] = [[cell.strip() for cell in header.strip("|").split("|")]]
    idx = start + 2
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or "|" not in stripped:
            break
        rows.append([cell.strip() for cell in stripped.strip("|").split("|")])
        idx += 1
    return rows, idx


def markdown_table_stats(markdown: str) -> Dict[str, int]:
    lines = markdown.splitlines()
    idx = 0
    tables = 0
    total_cells = 0
    max_cells = 0
    while idx < len(lines):
        table = parse_markdown_table(lines, idx)
        if not table:
            idx += 1
            continue
        rows, next_idx = table
        cells = sum(len(row) for row in rows)
        tables += 1
        total_cells += cells
        max_cells = max(max_cells, cells)
        idx = next_idx
    return {"tables": tables, "total_cells": total_cells, "max_cells": max_cells}


def choose_table_mode(markdown: str, requested: str) -> str:
    if requested != "auto":
        return requested
    stats = markdown_table_stats(markdown)
    # Native Feishu tables are best for small, editable tables. Larger or many
    # tables require many non-idempotent cell writes, so text mode is safer.
    if stats["tables"] <= 2 and stats["total_cells"] <= 36 and stats["max_cells"] <= 24:
        return "native"
    return "text"


def markdown_to_ops(markdown: str, base_dir: Optional[str] = None, table_mode: str = "native") -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = []
    lines = markdown.splitlines()
    idx = 0
    in_code = False
    code_lines: List[str] = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            ops.append({"type": "block", "block": text_block("text", 2, "\n".join(code_lines))})
            code_lines = []

    while idx < len(lines):
        line = lines[idx].rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
                code_lines = []
            idx += 1
            continue
        if in_code:
            code_lines.append(line)
            idx += 1
            continue
        if not stripped:
            idx += 1
            continue

        table = parse_markdown_table(lines, idx)
        if table:
            rows, next_idx = table
            if table_mode == "native":
                ops.append({"type": "table", "values": rows})
            elif table_mode == "text":
                widths = [0] * max((len(row) for row in rows), default=0)
                for row in rows:
                    for col_idx, cell in enumerate(row):
                        widths[col_idx] = max(widths[col_idx], len(cell))
                for row in rows:
                    padded = [cell.ljust(widths[col_idx]) for col_idx, cell in enumerate(row)]
                    ops.append({"type": "block", "block": text_block("text", 2, " | ".join(padded))})
            else:
                raise FeishuError(f"unknown table mode: {table_mode}")
            idx = next_idx
            continue

        image_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", stripped)
        if image_match:
            alt = image_match.group(1).strip()
            image_path = image_match.group(2).strip().strip('"').strip("'")
            if base_dir and not urllib.parse.urlparse(image_path).scheme and not os.path.isabs(image_path):
                image_path = os.path.join(base_dir, image_path)
            ops.append({"type": "image", "path": image_path, "alt": alt})
            if alt:
                ops.append({"type": "block", "block": text_block("text", 2, f"图：{alt}")})
            idx += 1
            continue

        if stripped.startswith("### "):
            block = text_block("heading3", 5, stripped[4:])
        elif stripped.startswith("## "):
            block = text_block("heading2", 4, stripped[3:])
        elif stripped.startswith("# "):
            block = text_block("heading1", 3, stripped[2:])
        elif stripped.startswith("- [ ] ") or stripped.startswith("- [x] ") or stripped.startswith("- [X] "):
            block = text_block("bullet", 12, stripped[2:])
        elif stripped.startswith("- "):
            block = text_block("bullet", 12, stripped[2:])
        elif re.match(r"^\d+\.\s+", stripped):
            block = text_block("ordered", 13, re.sub(r"^\d+\.\s+", "", stripped))
        elif stripped.startswith("> "):
            block = text_block("text", 2, f"引用：{stripped[2:]}")
        else:
            block = text_block("text", 2, stripped)
        ops.append({"type": "block", "block": block})
        idx += 1
    if in_code:
        flush_code()
    return ops


def write_ops_in_order(
    docx_token: str,
    token: str,
    ops: List[Dict[str, Any]],
    chunk_size: int,
) -> Dict[str, int]:
    index = 0
    written_blocks = 0
    table_count = 0
    image_count = 0
    pending_blocks: List[Dict[str, Any]] = []

    def flush_blocks() -> None:
        nonlocal index, written_blocks, pending_blocks
        while pending_blocks:
            chunk = pending_blocks[:chunk_size]
            del pending_blocks[:chunk_size]
            data = create_docx_children(docx_token, docx_token, token, chunk, index=index)
            if data.get("code") != 0:
                raise FeishuError(json.dumps(data, ensure_ascii=False, indent=2))
            index += len(chunk)
            written_blocks += len(chunk)
            time.sleep(0.35)

    for op in ops:
        op_type = op.get("type")
        if op_type == "block":
            pending_blocks.append(op["block"])
            if len(pending_blocks) >= chunk_size:
                flush_blocks()
        elif op_type == "table":
            flush_blocks()
            create_table_with_values(docx_token, token, op["values"], index=index)
            index += 1
            table_count += 1
        elif op_type == "image":
            flush_blocks()
            image_path = op["path"]
            if urllib.parse.urlparse(image_path).scheme:
                raise FeishuError("remote image URLs are not supported yet; download the image locally first")
            if not os.path.exists(image_path):
                raise FeishuError(f"image file not found: {image_path}")
            create_image_block_with_file(docx_token, token, image_path, index=index)
            index += 1
            image_count += 1
        else:
            raise FeishuError(f"unknown markdown op type: {op_type}")
    flush_blocks()
    return {"top_level_blocks": index, "written_text_blocks": written_blocks, "tables": table_count, "images": image_count}


def normalize_markdown_text(markdown: str, table_mode: str = "native") -> str:
    lines: List[str] = []
    in_code = False
    raw_lines = markdown.splitlines()
    idx = 0
    while idx < len(raw_lines):
        raw_line = raw_lines[idx]
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            idx += 1
            continue
        if not stripped:
            idx += 1
            continue
        table = None if in_code else parse_markdown_table(raw_lines, idx)
        if table:
            rows, next_idx = table
            if table_mode == "native":
                for row in rows:
                    lines.extend(cell for cell in row if cell)
            elif table_mode == "text":
                widths = [0] * max((len(row) for row in rows), default=0)
                for row in rows:
                    for col_idx, cell in enumerate(row):
                        widths[col_idx] = max(widths[col_idx], len(cell))
                for row in rows:
                    padded = [cell.ljust(widths[col_idx]) for col_idx, cell in enumerate(row)]
                    lines.append(" | ".join(padded).rstrip())
            else:
                raise FeishuError(f"unknown table mode: {table_mode}")
            idx = next_idx
            continue
        image_match = None if in_code else re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", stripped)
        if image_match:
            alt = image_match.group(1).strip()
            if alt:
                lines.append(f"图：{alt}")
            idx += 1
            continue
        if not in_code:
            heading_match = re.match(r"^#{1,9}\s+(.+)$", stripped)
            if heading_match:
                stripped = heading_match.group(1)
            elif stripped.startswith("> "):
                stripped = f"引用：{stripped[2:]}"
            else:
                stripped = re.sub(r"^[-*]\s+", "", stripped)
                stripped = re.sub(r"^\d+\.\s+", "", stripped)
        lines.append(stripped)
        idx += 1
    return "\n".join(lines)


def strip_trailing_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


def generated_fixture(sections: int, paragraphs_per_section: int) -> str:
    lines = [
        "# Feishu Roundtrip Validation",
        "这是一份由 feishu-docs skill 自动生成的长文档写入验证材料。",
        "The purpose is to detect ordering, truncation, and block conversion issues.",
    ]
    for section in range(1, sections + 1):
        lines.append("")
        lines.append(f"## Section {section:02d} 标题")
        for paragraph in range(1, paragraphs_per_section + 1):
            marker = f"S{section:02d}-P{paragraph:02d}"
            lines.append(
                f"{marker} 正文段落：用于检查长文档写入后的顺序、中文字符、English words, numbers {section * paragraph}, and URL https://example.com/{marker}."
            )
        lines.append(f"- S{section:02d}-B01 bullet item alpha")
        lines.append(f"- S{section:02d}-B02 bullet item beta")
        lines.append(f"1. S{section:02d}-O01 ordered item one")
        lines.append(f"2. S{section:02d}-O02 ordered item two")
    return "\n".join(lines) + "\n"


def generated_prd_fixture(image_path: str, sections: int = 6) -> str:
    lines = [
        "# 智能批改工作台 PRD",
        "## 1. 背景与目标",
        "当前教研与运营团队需要一个稳定的工作台来管理批改任务、查看风险、追踪转化线索。",
        "- [ ] 明确 MVP 范围",
        "- [x] 对齐核心数据指标",
        "## 2. 用户与场景",
        "| 角色 | 核心诉求 | 高频动作 |",
        "| --- | --- | --- |",
        "| 教师 | 快速定位待处理作业 | 批改、备注、反馈 |",
        "| 教研 | 发现共性薄弱点 | 查看统计、调整题单 |",
        "| 运营 | 识别高意向用户 | 查看转化信号、触达 |",
        "## 3. 核心流程",
        "1. 用户提交作业",
        "2. 系统识别题型与风险",
        "3. 教师完成批改并生成反馈",
        "4. 运营查看转化建议",
        f"![工作台信息架构示意图]({image_path})",
        "## 4. 指标口径",
        "| 指标 | 定义 | 目标值 |",
        "| --- | --- | --- |",
        "| 首响时长 | 从提交到首次批改动作的时间 | 小于 10 分钟 |",
        "| 完成率 | 当日完成批改任务 / 当日新任务 | 大于 95% |",
        "| 反馈采纳率 | 用户查看反馈后的下一步动作比例 | 大于 60% |",
    ]
    for section in range(1, sections + 1):
        lines.extend(
            [
                f"## 5.{section} 功能模块 {section}",
                f"模块 {section} 需要覆盖正常态、空状态、错误态和权限不足状态。",
                "| 页面区域 | 字段 | 交互 | 验收标准 |",
                "| --- | --- | --- | --- |",
                f"| 列表区 | 任务编号 S{section:02d} | 点击进入详情 | 顺序稳定且不丢失 |",
                f"| 详情区 | 学生反馈 S{section:02d} | 支持编辑保存 | 回读内容一致 |",
                f"- 风险点 S{section:02d}-A：长文本不要截断",
                f"- 风险点 S{section:02d}-B：表格不要错列",
                f"1. 验收步骤 S{section:02d}-1",
                f"2. 验收步骤 S{section:02d}-2",
            ]
        )
    lines.extend(
        [
            "## 6. 非功能要求",
            "> 所有写入链路必须支持回读校验，避免 PRD 发布后内容错乱。",
            "```",
            "status = roundtrip_verify(document)",
            "assert status.matched is True",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_blocks_in_chunks(
    docx_token: str,
    token: str,
    blocks: List[Dict[str, Any]],
    chunk_size: int,
) -> int:
    index = 0
    written = 0
    for start in range(0, len(blocks), chunk_size):
        chunk = blocks[start : start + chunk_size]
        data = create_docx_children(docx_token, docx_token, token, chunk, index=index)
        if data.get("code") != 0:
            raise FeishuError(json.dumps(data, ensure_ascii=False, indent=2))
        written += len(chunk)
        index += len(chunk)
        time.sleep(0.4)
    return written


def element_text(elements: List[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for element in elements or []:
        text_run = element.get("text_run")
        if text_run:
            chunks.append(text_run.get("content", ""))
    return "".join(chunks)


def block_text(block: Dict[str, Any]) -> Optional[str]:
    for key in (
        "page",
        "text",
        "heading1",
        "heading2",
        "heading3",
        "heading4",
        "heading5",
        "heading6",
        "heading7",
        "heading8",
        "heading9",
        "bullet",
        "ordered",
        "code",
        "quote",
        "todo",
    ):
        value = block.get(key)
        if isinstance(value, dict):
            text = element_text(value.get("elements", []))
            if text:
                return text
    return None


def blocks_to_text(items: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for block in items:
        text = block_text(block)
        if text:
            lines.append(text)
    return "\n".join(lines)


def extract_document_id(create_response: Dict[str, Any]) -> str:
    data = create_response.get("data", {})
    document = data.get("document", {})
    doc_id = (
        document.get("document_id")
        or document.get("document_token")
        or data.get("document_id")
        or data.get("document_token")
    )
    if not doc_id:
        raise FeishuError(f"cannot find document id in response: {json.dumps(create_response, ensure_ascii=False)}")
    return doc_id


def command_doctor(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    data = tenant_access_token()
    output = dict(data)
    if "tenant_access_token" in output:
        output["tenant_access_token"] = mask_token(output["tenant_access_token"])
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if data.get("code") == 0 else 1


def command_resolve_url(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    data = resolve_url(args.url, token)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data.get("code") == 0 else 1


def command_read_url(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    resolved = resolve_url(args.url, token)
    if resolved.get("code") != 0:
        print(json.dumps(resolved, ensure_ascii=False, indent=2))
        return 1

    node = resolved.get("data", {}).get("node", {})
    obj_type = node.get("obj_type")
    obj_token = node.get("obj_token")
    if obj_type == "docx":
        data = docx_blocks(obj_token, token, page_size=args.page_size)
        if args.format == "json":
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            items = data.get("data", {}).get("items", [])
            print(blocks_to_text(items))
        return 0 if data.get("code") == 0 else 1

    print(
        json.dumps(
            {
                "code": 0,
                "msg": "resolved but read-url currently supports docx text extraction only",
                "obj_type": obj_type,
                "obj_token": obj_token,
                "node": node,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_create_docx(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    data = create_docx(args.title, token, folder_token=args.folder_token)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data.get("code") == 0 else 1


def command_append_docx_md(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    with open(args.markdown, "r", encoding="utf-8") as fh:
        markdown = fh.read()
    ops = markdown_to_ops(
        markdown,
        base_dir=os.path.dirname(os.path.abspath(args.markdown)),
        table_mode=args.table_mode,
    )
    stats = write_ops_in_order(args.docx_token, token, ops, chunk_size=args.chunk_size)
    print(json.dumps({"code": 0, "docx_token": args.docx_token, **stats}, ensure_ascii=False, indent=2))
    return 0


def create_docx_from_markdown(
    markdown: str,
    token: str,
    title: str,
    folder_token: Optional[str],
    base_dir: Optional[str],
    chunk_size: int,
    table_mode: str = "native",
) -> Tuple[str, Dict[str, int]]:
    create_response = create_docx(title, token, folder_token=folder_token)
    if create_response.get("code") != 0:
        raise FeishuError(json.dumps(create_response, ensure_ascii=False, indent=2))
    docx_token = extract_document_id(create_response)
    resolved_table_mode = choose_table_mode(markdown, table_mode)
    ops = markdown_to_ops(markdown, base_dir=base_dir, table_mode=resolved_table_mode)
    stats = write_ops_in_order(docx_token, token, ops, chunk_size=chunk_size)
    stats["table_mode"] = resolved_table_mode
    return docx_token, stats


def command_roundtrip_docx(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    if args.markdown:
        with open(args.markdown, "r", encoding="utf-8") as fh:
            markdown = fh.read()
    else:
        markdown = generated_fixture(args.sections, args.paragraphs_per_section)

    resolved_table_mode = choose_table_mode(markdown, args.table_mode)
    expected = strip_trailing_ws(normalize_markdown_text(markdown, table_mode=resolved_table_mode))
    base_dir = os.path.dirname(os.path.abspath(args.markdown)) if args.markdown else None
    try:
        docx_token, stats = create_docx_from_markdown(
            markdown,
            token,
            title=args.title,
            folder_token=args.folder_token,
            base_dir=base_dir,
            chunk_size=args.chunk_size,
            table_mode=args.table_mode,
        )
    except FeishuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    time.sleep(args.settle_seconds)
    actual_blocks = all_docx_blocks(docx_token, token, page_size=100)
    # Skip the root page block title; compare inserted content only.
    actual = strip_trailing_ws(blocks_to_text([block for block in actual_blocks if block.get("block_id") != docx_token]))

    diff = list(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )
    result = {
        "code": 0 if not diff else 1,
        "docx_token": docx_token,
        "title": args.title,
        "expected_lines": len(expected.splitlines()),
        "actual_lines": len(actual.splitlines()),
        **stats,
        "read_blocks": len(actual_blocks),
        "matched": not diff,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if diff:
        print("\n".join(diff[: args.max_diff_lines]))
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        with open(os.path.join(args.output_dir, "expected.txt"), "w", encoding="utf-8") as fh:
            fh.write(expected + "\n")
        with open(os.path.join(args.output_dir, "actual.txt"), "w", encoding="utf-8") as fh:
            fh.write(actual + "\n")
        with open(os.path.join(args.output_dir, "source.md"), "w", encoding="utf-8") as fh:
            fh.write(markdown)
    return 0 if not diff else 1


def command_write_prd_md(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    with open(args.markdown, "r", encoding="utf-8") as fh:
        markdown = fh.read()
    base_dir = os.path.dirname(os.path.abspath(args.markdown))
    title = args.title
    if not title:
        first_heading = next((line.strip()[2:].strip() for line in markdown.splitlines() if line.strip().startswith("# ")), None)
        title = first_heading or os.path.splitext(os.path.basename(args.markdown))[0]
    docx_token, stats = create_docx_from_markdown(
        markdown,
        token,
        title=title,
        folder_token=args.folder_token,
        base_dir=base_dir,
        chunk_size=args.chunk_size,
        table_mode=args.table_mode,
    )
    print(json.dumps({"code": 0, "docx_token": docx_token, "title": title, **stats}, ensure_ascii=False, indent=2))
    return 0


def command_write_doc_md(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    with open(args.markdown, "r", encoding="utf-8") as fh:
        markdown = fh.read()
    base_dir = os.path.dirname(os.path.abspath(args.markdown))
    title = args.title
    if not title:
        first_heading = next((line.strip()[2:].strip() for line in markdown.splitlines() if line.strip().startswith("# ")), None)
        title = first_heading or os.path.splitext(os.path.basename(args.markdown))[0]
    docx_token, stats = create_docx_from_markdown(
        markdown,
        token,
        title=title,
        folder_token=args.folder_token,
        base_dir=base_dir,
        chunk_size=args.chunk_size,
        table_mode=args.table_mode,
    )
    print(json.dumps({"code": 0, "docx_token": docx_token, "title": title, **stats}, ensure_ascii=False, indent=2))
    return 0


def command_roundtrip_prd(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    temp_dir = tempfile.mkdtemp(prefix="feishu-docs-prd-")
    image_path = args.image
    if not image_path:
        image_path = os.path.join(temp_dir, "prd-diagram.png")
        write_sample_png(image_path)
    markdown = generated_prd_fixture(image_path=image_path, sections=args.sections)
    resolved_table_mode = choose_table_mode(markdown, args.table_mode)
    expected = strip_trailing_ws(normalize_markdown_text(markdown, table_mode=resolved_table_mode))
    docx_token, stats = create_docx_from_markdown(
        markdown,
        token,
        title=args.title,
        folder_token=args.folder_token,
        base_dir=temp_dir,
        chunk_size=args.chunk_size,
        table_mode=args.table_mode,
    )
    time.sleep(args.settle_seconds)
    actual_blocks = all_docx_blocks(docx_token, token, page_size=100)
    actual = strip_trailing_ws(blocks_to_text([block for block in actual_blocks if block.get("block_id") != docx_token]))
    diff = list(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )
    image_blocks = [block for block in actual_blocks if block.get("image")]
    table_blocks = [block for block in actual_blocks if block.get("table")]
    expected_table_blocks = stats["tables"] if stats["table_mode"] == "native" else 0
    result = {
        "code": 0 if not diff and image_blocks and len(table_blocks) == expected_table_blocks else 1,
        "docx_token": docx_token,
        "title": args.title,
        **stats,
        "expected_lines": len(expected.splitlines()),
        "actual_lines": len(actual.splitlines()),
        "read_blocks": len(actual_blocks),
        "table_blocks": len(table_blocks),
        "image_blocks": len(image_blocks),
        "text_matched": not diff,
        "table_mode": stats["table_mode"],
        "matched": bool(not diff and image_blocks and len(table_blocks) == expected_table_blocks),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if diff:
        print("\n".join(diff[: args.max_diff_lines]))
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        with open(os.path.join(args.output_dir, "source.md"), "w", encoding="utf-8") as fh:
            fh.write(markdown)
        with open(os.path.join(args.output_dir, "expected.txt"), "w", encoding="utf-8") as fh:
            fh.write(expected + "\n")
        with open(os.path.join(args.output_dir, "actual.txt"), "w", encoding="utf-8") as fh:
            fh.write(actual + "\n")
    return 0 if result["matched"] else 1


def command_roundtrip_media(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = get_token_or_raise()
    title = args.title
    create_response = create_docx(title, token, folder_token=args.folder_token)
    if create_response.get("code") != 0:
        print(json.dumps(create_response, ensure_ascii=False, indent=2))
        return 1
    docx_token = extract_document_id(create_response)
    intro = [
        text_block("heading1", 3, "Feishu media roundtrip validation"),
        text_block("text", 2, "This document validates table and image insertion."),
    ]
    intro_response = create_docx_children(docx_token, docx_token, token, intro, index=0)
    if intro_response.get("code") != 0:
        print(json.dumps(intro_response, ensure_ascii=False, indent=2))
        return 1

    table_values = [
        ["Metric", "Expected", "Actual"],
        ["Rows", "3", "3"],
        ["Status", "OK", "OK"],
    ]
    result: Dict[str, Any] = {
        "code": 0,
        "title": title,
        "docx_token": docx_token,
        "table": {"attempted": True, "created": False, "validated": False},
        "image": {"attempted": True, "created": False, "validated": False},
    }

    table_info = create_table_with_values(docx_token, token, table_values, index=-1)
    result["table"].update({"created": True, "table_id": table_info["table_id"], "cell_count": len(table_info["cells"])})

    image_path = args.image
    temp_dir: Optional[str] = None
    if not image_path:
        temp_dir = tempfile.mkdtemp(prefix="feishu-docs-media-")
        image_path = os.path.join(temp_dir, "sample.png")
        write_sample_png(image_path)
    image_info = create_image_block_with_file(docx_token, token, image_path, index=-1)
    result["image"].update(
        {
            "created": True,
            "image_block_id": image_info["image_block_id"],
            "file_token_masked": mask_token(image_info["file_token"]),
        }
    )

    time.sleep(args.settle_seconds)
    blocks = all_docx_blocks(docx_token, token, page_size=100)
    text = blocks_to_text(blocks)
    table_markers = [cell for row in table_values for cell in row]
    result["table"]["validated"] = all(marker in text for marker in table_markers)
    image_block = next((block for block in blocks if block.get("block_id") == image_info["image_block_id"]), None)
    result["image"]["validated"] = bool(image_block and image_block.get("image"))
    result["read_blocks"] = len(blocks)
    result["matched"] = bool(result["table"]["validated"] and result["image"]["validated"])
    if temp_dir:
        result["sample_image"] = image_path
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["matched"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Feishu/Lark Docs helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="validate credentials and tenant token")
    doctor.add_argument("--env", help="optional env file with FEISHU_APP_ID and FEISHU_APP_SECRET")
    doctor.set_defaults(func=command_doctor)

    resolve = subparsers.add_parser("resolve-url", help="resolve a Feishu URL, including Wiki node URLs")
    resolve.add_argument("url")
    resolve.add_argument("--env", help="optional env file")
    resolve.set_defaults(func=command_resolve_url)

    read = subparsers.add_parser("read-url", help="read a Feishu URL; currently extracts Docx block text")
    read.add_argument("url")
    read.add_argument("--env", help="optional env file")
    read.add_argument("--format", choices=["text", "json"], default="text")
    read.add_argument("--page-size", type=int, default=50)
    read.set_defaults(func=command_read_url)

    create = subparsers.add_parser("create-docx", help="create a blank Docx document")
    create.add_argument("title")
    create.add_argument("--env", help="optional env file")
    create.add_argument("--folder-token", help="optional destination folder token")
    create.set_defaults(func=command_create_docx)

    append = subparsers.add_parser("append-docx-md", help="append a Markdown subset to an existing Docx document")
    append.add_argument("docx_token")
    append.add_argument("markdown")
    append.add_argument("--env", help="optional env file")
    append.add_argument("--chunk-size", type=int, default=20)
    append.add_argument("--table-mode", choices=["auto", "native", "text"], default="auto")
    append.set_defaults(func=command_append_docx_md)

    write_doc = subparsers.add_parser("write-doc-md", help="create a Docx document from Markdown with automatic content-based handling")
    write_doc.add_argument("markdown")
    write_doc.add_argument("--env", help="optional env file")
    write_doc.add_argument("--title", help="document title; defaults to first H1 or filename")
    write_doc.add_argument("--folder-token", help="optional destination folder token")
    write_doc.add_argument("--chunk-size", type=int, default=20)
    write_doc.add_argument("--table-mode", choices=["auto", "native", "text"], default="auto")
    write_doc.set_defaults(func=command_write_doc_md)

    write_prd = subparsers.add_parser("write-prd-md", help="create a Docx document from PRD Markdown with tables and local images")
    write_prd.add_argument("markdown")
    write_prd.add_argument("--env", help="optional env file")
    write_prd.add_argument("--title", help="document title; defaults to first H1 or filename")
    write_prd.add_argument("--folder-token", help="optional destination folder token")
    write_prd.add_argument("--chunk-size", type=int, default=20)
    write_prd.add_argument("--table-mode", choices=["auto", "native", "text"], default="auto")
    write_prd.set_defaults(func=command_write_prd_md)

    roundtrip = subparsers.add_parser("roundtrip-docx", help="create, write, read back, and diff a Docx test document")
    roundtrip.add_argument("--env", help="optional env file")
    roundtrip.add_argument("--title", default="feishu-docs roundtrip validation")
    roundtrip.add_argument("--folder-token", help="optional destination folder token")
    roundtrip.add_argument("--markdown", help="optional Markdown fixture; generated when omitted")
    roundtrip.add_argument("--sections", type=int, default=8)
    roundtrip.add_argument("--paragraphs-per-section", type=int, default=4)
    roundtrip.add_argument("--chunk-size", type=int, default=20)
    roundtrip.add_argument("--table-mode", choices=["auto", "native", "text"], default="auto")
    roundtrip.add_argument("--settle-seconds", type=float, default=1.5)
    roundtrip.add_argument("--max-diff-lines", type=int, default=120)
    roundtrip.add_argument("--output-dir", help="write source/expected/actual comparison files")
    roundtrip.set_defaults(func=command_roundtrip_docx)

    media = subparsers.add_parser("roundtrip-media", help="create, write, and validate a Docx table plus image")
    media.add_argument("--env", help="optional env file")
    media.add_argument("--title", default="feishu-docs media validation")
    media.add_argument("--folder-token", help="optional destination folder token")
    media.add_argument("--image", help="optional local image path; a tiny PNG is generated when omitted")
    media.add_argument("--settle-seconds", type=float, default=2.0)
    media.set_defaults(func=command_roundtrip_media)

    prd = subparsers.add_parser("roundtrip-prd", help="create, write, and validate a PRD-style Docx with tables and image")
    prd.add_argument("--env", help="optional env file")
    prd.add_argument("--title", default="feishu-docs PRD validation")
    prd.add_argument("--folder-token", help="optional destination folder token")
    prd.add_argument("--image", help="optional local image path; a tiny PNG is generated when omitted")
    prd.add_argument("--sections", type=int, default=6)
    prd.add_argument("--chunk-size", type=int, default=16)
    prd.add_argument("--table-mode", choices=["auto", "native", "text"], default="auto")
    prd.add_argument("--settle-seconds", type=float, default=2.0)
    prd.add_argument("--max-diff-lines", type=int, default=160)
    prd.add_argument("--output-dir", help="write source/expected/actual comparison files")
    prd.set_defaults(func=command_roundtrip_prd)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except FeishuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
