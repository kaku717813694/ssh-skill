"""
Obsidian 受控资料凭据查询。

仅在显式配置环境变量时启用受控资料查找。优先查找指定的
`各项密码.md`，如未命中则扫描同目录下其他 Markdown 文件。
仅返回运行时所需密码，不向配置文件回写。
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Optional


PASSWORD_FILE_ENV = "SSH_SKILL_OBSIDIAN_PASSWORD_FILE"
CONTROLLED_DIR_ENV = "SSH_SKILL_OBSIDIAN_CONTROLLED_DIR"


def _get_env_path(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if not value:
        return None
    value = value.strip()
    return value or None


def _primary_password_file() -> Optional[str]:
    return _get_env_path(PASSWORD_FILE_ENV)


def _controlled_dir() -> Optional[str]:
    configured_dir = _get_env_path(CONTROLLED_DIR_ENV)
    if configured_dir:
        return configured_dir

    primary = _primary_password_file()
    if primary:
        return os.path.dirname(primary)

    return None


def _iter_markdown_files() -> Iterable[str]:
    primary = _primary_password_file()
    yielded = set()

    if primary and os.path.exists(primary):
        yielded.add(os.path.normcase(primary))
        yield primary

    controlled_dir = _controlled_dir()
    if not controlled_dir or not os.path.isdir(controlled_dir):
        return

    for name in sorted(os.listdir(controlled_dir)):
        if not name.lower().endswith(".md"):
            continue
        path = os.path.join(controlled_dir, name)
        normalized = os.path.normcase(path)
        if normalized in yielded:
            continue
        yielded.add(normalized)
        yield path


def _parse_markdown_table(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped.startswith("|"):
                    continue
                columns = [part.strip() for part in stripped.strip("|").split("|")]
                if len(columns) < 5:
                    continue
                first = columns[0].lower()
                if first in {"ip", "---", "序号"}:
                    continue
                yield {
                    "ip": columns[0],
                    "hostname": columns[1],
                    "device_type": columns[2],
                    "user": columns[3],
                    "password": columns[4],
                    "source": path,
                }
    except OSError:
        return


def _score_record(
    record: Dict[str, str],
    hostname: Optional[str],
    alias: Optional[str],
    user: Optional[str],
    metadata: Optional[Dict[str, object]],
) -> int:
    score = 0
    record_ip = record["ip"].strip().lower()
    record_host = record["hostname"].strip().lower()
    record_user = record["user"].strip().lower()

    hostname = (hostname or "").strip().lower()
    alias = (alias or "").strip().lower()
    user = (user or "").strip().lower()

    if hostname and hostname == record_ip:
        score += 100
    if hostname and hostname == record_host:
        score += 80
    if alias and alias == record_host:
        score += 60
    if user and user == record_user:
        score += 15

    if metadata:
        description = str(metadata.get("description", "")).lower()
        if record_host and record_host in description:
            score += 12
        if record_ip and record_ip in description:
            score += 12

    return score


def lookup_password(
    hostname: Optional[str] = None,
    alias: Optional[str] = None,
    user: Optional[str] = None,
    metadata: Optional[Dict[str, object]] = None,
) -> Optional[str]:
    """
    从 Obsidian 受控资料中查找密码。

    优先使用 IP、主机名精确匹配；存在多个命中时优先用户名一致的记录。
    """
    best_score = 0
    best_password: Optional[str] = None

    for path in _iter_markdown_files():
        for record in _parse_markdown_table(path):
            password = record["password"].strip()
            if not password:
                continue
            score = _score_record(record, hostname, alias, user, metadata)
            if score > best_score:
                best_score = score
                best_password = password

    return best_password
