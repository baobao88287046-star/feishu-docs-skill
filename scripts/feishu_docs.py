#!/usr/bin/env python3
"""Small Feishu/Lark document helper for Codex skills.

The script intentionally avoids external dependencies. It reads credentials from
environment variables or a simple KEY=VALUE env file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
