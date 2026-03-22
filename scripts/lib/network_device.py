"""
网络设备交互执行辅助模块。

面向传统网络设备 CLI 的最小可用适配层，提供：
- 厂商 profile（分页、配置模式、保存命令）
- 多命令拆分
- 交互式 shell 执行
- 分页和确认提示自动应答
- 常见错误模式识别
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


DEFAULT_PROMPT_PATTERNS = [
    re.compile(r"(?m)(?:^|\n)\S+[>#]\s*$"),
    re.compile(r"(?m)(?:^|\n).+ [#$>]\s*$"),
    re.compile(r"(?m)(?:^|\n)<[^>\n]+>\s*$"),
    re.compile(r"(?m)(?:^|\n)\[[^\]\n]+\]\s*$"),
]

DEFAULT_MORE_PATTERNS = [
    re.compile(r"--More--", re.IGNORECASE),
    re.compile(r"---- More ----", re.IGNORECASE),
    re.compile(r"press any key to continue", re.IGNORECASE),
    re.compile(r"more", re.IGNORECASE),
]

DEFAULT_CONFIRM_RULES = [
    (re.compile(r"\[[Yy]/[Nn]\]"), "Y\n"),
    (re.compile(r"\[[Yy]/[Nn]/[Cc]\]"), "Y\n"),
    (re.compile(r"\(yes/no\)", re.IGNORECASE), "yes\n"),
    (re.compile(r"\[confirm\]", re.IGNORECASE), "\n"),
]

DEFAULT_ERROR_PATTERNS = [
    re.compile(r"% ?invalid input", re.IGNORECASE),
    re.compile(r"% ?incomplete command", re.IGNORECASE),
    re.compile(r"% ?ambiguous command", re.IGNORECASE),
    re.compile(r"% ?unknown command", re.IGNORECASE),
    re.compile(r"unknown command", re.IGNORECASE),
    re.compile(r"unrecognized command", re.IGNORECASE),
    re.compile(r"syntax error", re.IGNORECASE),
    re.compile(r"incomplete command", re.IGNORECASE),
    re.compile(r"error:", re.IGNORECASE),
]


@dataclass(frozen=True)
class DeviceProfile:
    vendor: str
    disable_paging_commands: Tuple[str, ...] = ()
    enter_config_command: Optional[str] = None
    exit_config_command: Optional[str] = None
    save_command: Optional[str] = None
    save_in_config_mode: bool = False
    prompt_patterns: Tuple[re.Pattern, ...] = tuple(DEFAULT_PROMPT_PATTERNS)
    more_patterns: Tuple[re.Pattern, ...] = tuple(DEFAULT_MORE_PATTERNS)
    confirm_rules: Tuple[Tuple[re.Pattern, str], ...] = tuple(DEFAULT_CONFIRM_RULES)
    error_patterns: Tuple[re.Pattern, ...] = tuple(DEFAULT_ERROR_PATTERNS)
    command_shortcuts: Dict[str, str] = None


_PROFILES: Dict[str, DeviceProfile] = {
    "generic": DeviceProfile(vendor="generic"),
    "cisco": DeviceProfile(
        vendor="cisco",
        disable_paging_commands=("terminal length 0",),
        enter_config_command="configure terminal",
        exit_config_command="end",
        save_command="write memory",
        error_patterns=tuple(DEFAULT_ERROR_PATTERNS) + (
            re.compile(r"% ?.*", re.IGNORECASE),
        ),
    ),
    "arista": DeviceProfile(
        vendor="arista",
        disable_paging_commands=("terminal length 0",),
        enter_config_command="configure terminal",
        exit_config_command="end",
        save_command="write memory",
        error_patterns=tuple(DEFAULT_ERROR_PATTERNS) + (
            re.compile(r"% ?.*", re.IGNORECASE),
        ),
    ),
    "huawei": DeviceProfile(
        vendor="huawei",
        disable_paging_commands=("screen-length 0 temporary",),
        enter_config_command="system-view",
        exit_config_command="return",
        save_command="save",
        prompt_patterns=(
            re.compile(r"(?m)(?:^|\n)<[^>\n]+>\s*$"),
            re.compile(r"(?m)(?:^|\n)\[[~\*]?[^\]\n]+\]\s*$"),
        ),
        confirm_rules=tuple(DEFAULT_CONFIRM_RULES) + (
            (re.compile(r"continue\? ?\[y/n\]", re.IGNORECASE), "Y\n"),
            (re.compile(r"are you sure to continue\? ?\[y/n\]", re.IGNORECASE), "Y\n"),
        ),
        error_patterns=tuple(DEFAULT_ERROR_PATTERNS) + (
            re.compile(r"wrong parameter found", re.IGNORECASE),
            re.compile(r"too many parameters", re.IGNORECASE),
            re.compile(r"error: unrecognized command", re.IGNORECASE),
        ),
        command_shortcuts={
            "@uptime": "display version | include uptime",
            "@version": "display version",
        },
    ),
    "h3c": DeviceProfile(
        vendor="h3c",
        disable_paging_commands=("screen-length disable",),
        enter_config_command="system-view",
        exit_config_command="return",
        save_command="save force",
        prompt_patterns=(
            re.compile(r"(?m)(?:^|\n)<[^>\n]+>\s*$"),
            re.compile(r"(?m)(?:^|\n)\[[^\]\n]+\]\s*$"),
        ),
        confirm_rules=tuple(DEFAULT_CONFIRM_RULES) + (
            (re.compile(r"continue\? ?\[y/n\]", re.IGNORECASE), "Y\n"),
        ),
        error_patterns=tuple(DEFAULT_ERROR_PATTERNS) + (
            re.compile(r"wrong parameter found", re.IGNORECASE),
            re.compile(r"too many parameters", re.IGNORECASE),
            re.compile(r"% unrecognized command", re.IGNORECASE),
        ),
        command_shortcuts={
            "@uptime": "display version | include uptime",
            "@version": "display version",
        },
    ),
    "fortigate": DeviceProfile(
        vendor="fortigate",
        prompt_patterns=(
            re.compile(r"(?m)(?:^|\n)[A-Za-z0-9_.-]+(?: \([^)]+\))? [#$]\s*$"),
            re.compile(r"(?m)(?:^|\n)[A-Za-z0-9_.-]+(?: \([^)]+\))? >\s*$"),
        ),
        confirm_rules=tuple(DEFAULT_CONFIRM_RULES) + (
            (re.compile(r"do you want to continue\? ?\(y/n\)", re.IGNORECASE), "y\n"),
            (re.compile(r"continue\? ?\(y/n\)", re.IGNORECASE), "y\n"),
        ),
        error_patterns=tuple(DEFAULT_ERROR_PATTERNS) + (
            re.compile(r"command fail(?:ed)?", re.IGNORECASE),
            re.compile(r"unknown action", re.IGNORECASE),
            re.compile(r"parse error", re.IGNORECASE),
            re.compile(r"node_check_object fail", re.IGNORECASE),
        ),
        command_shortcuts={
            "@status": "get system status",
            "@ha": "get system ha status",
            "@perf": "get system performance status",
            "@version": "get system status",
        },
    ),
    "juniper": DeviceProfile(
        vendor="juniper",
        disable_paging_commands=("set cli screen-length 0", "set cli screen-width 0"),
        enter_config_command="configure",
        exit_config_command="exit configuration-mode",
        save_command="commit and-quit",
        save_in_config_mode=True,
        error_patterns=tuple(DEFAULT_ERROR_PATTERNS) + (
            re.compile(r"commit failed", re.IGNORECASE),
        ),
    ),
}

_VENDOR_ALIASES = {
    "ios": "cisco",
    "iosxe": "cisco",
    "ios-xe": "cisco",
    "nxos": "cisco",
    "nx-os": "cisco",
    "eos": "arista",
    "vrp": "huawei",
    "comware": "h3c",
    "junos": "juniper",
    "fortios": "fortigate",
    "fortigate": "fortigate",
    "fortinet": "fortigate",
}

_NETWORK_TOKENS = (
    "switch",
    "router",
    "firewall",
    "network",
    "huawei",
    "h3c",
    "juniper",
    "arista",
    "fortigate",
    "fortinet",
    "fortios",
    "ac",
    "poe",
)

_ALIAS_VENDOR_RULES = [
    (re.compile(r"^(?:poe-\d+|ac\d+|core|aggregation-\d+)$", re.IGNORECASE), "huawei"),
    (re.compile(r"^\d+-jr-\d+$", re.IGNORECASE), "h3c"),
    (re.compile(r"^(?:fw\d*|firewall|route)$", re.IGNORECASE), "fortigate"),
]

_MODEL_VENDOR_RULES = [
    (re.compile(r"\b(?:s5735|s67\d{2}|s77\d{2}|futurematrix)\b", re.IGNORECASE), "huawei"),
    (re.compile(r"\b(?:s5048|s1850|s5120|comware)\b", re.IGNORECASE), "h3c"),
    (re.compile(r"\bfortigate\b|\bfg[0-9a-z-]+\b", re.IGNORECASE), "fortigate"),
]


def normalize_vendor(vendor: Optional[str]) -> str:
    """规范化厂商标识。"""
    if not vendor:
        return "generic"
    normalized = vendor.strip().lower().replace(" ", "").replace("_", "-")
    return _VENDOR_ALIASES.get(normalized, normalized)


def get_device_profile(vendor: Optional[str]) -> DeviceProfile:
    """按厂商返回 profile，未知厂商回退到 generic。"""
    return _PROFILES.get(normalize_vendor(vendor), _PROFILES["generic"])


def is_network_metadata(metadata: Optional[Dict[str, object]]) -> bool:
    """根据元数据粗略判断是否为网络设备。"""
    if not metadata:
        return False

    tags = metadata.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    search_space = " ".join(
        str(item).lower()
        for item in [
            metadata.get("device_type"),
            metadata.get("device_vendor"),
            metadata.get("platform"),
            metadata.get("role"),
            metadata.get("description"),
            metadata.get("hostname"),
            metadata.get("model"),
            *tags,
        ]
        if item
    )
    return any(
        token in search_space
        for token in _NETWORK_TOKENS
    )


def vendor_from_metadata(metadata: Optional[Dict[str, object]]) -> str:
    """从元数据推断厂商。"""
    if not metadata:
        return "generic"

    for key in ("device_vendor", "platform", "device_type", "role", "environment"):
        value = metadata.get(key)
        if not value:
            continue
        normalized = normalize_vendor(str(value))
        if normalized in _PROFILES:
            return normalized

    tags = metadata.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    for tag in tags:
        normalized = normalize_vendor(str(tag))
        if normalized in _PROFILES:
            return normalized

    for key in ("model", "description", "hostname"):
        value = metadata.get(key)
        if not value:
            continue
        text = str(value)
        for pattern, vendor in _MODEL_VENDOR_RULES:
            if pattern.search(text):
                return vendor

    return "generic"


def vendor_from_alias(alias: Optional[str]) -> str:
    """根据别名推断厂商，优先适配当前现网命名。"""
    if not alias:
        return "generic"
    for pattern, vendor in _ALIAS_VENDOR_RULES:
        if pattern.match(alias.strip()):
            return vendor
    return "generic"


def vendor_from_context(alias: Optional[str], metadata: Optional[Dict[str, object]]) -> str:
    """综合别名和元数据推断厂商。"""
    vendor = vendor_from_metadata(metadata)
    if vendor != "generic":
        return vendor
    return vendor_from_alias(alias)


def is_network_target(alias: Optional[str], metadata: Optional[Dict[str, object]]) -> bool:
    """综合判断目标是否像网络设备。"""
    if is_network_metadata(metadata):
        return True
    return vendor_from_alias(alias) != "generic"


def split_command_text(command_text: str, delimiter: str = ";;") -> List[str]:
    """把命令文本拆分成多条命令。"""
    if delimiter and delimiter in command_text:
        parts = command_text.split(delimiter)
    else:
        lines = [line.strip() for line in command_text.splitlines() if line.strip()]
        parts = lines if len(lines) > 1 else [command_text]
    return [part.strip() for part in parts if part.strip()]


def expand_command_shortcuts(commands: Sequence[str], vendor: Optional[str]) -> List[str]:
    """将快捷命令展开为厂商专用命令。"""
    profile = get_device_profile(vendor)
    shortcuts = profile.command_shortcuts or {}
    expanded: List[str] = []
    for command in commands:
        expanded.append(shortcuts.get(command.strip(), command))
    return expanded


def detect_error(output: str, profile: DeviceProfile) -> Optional[str]:
    """从命令输出里提取第一个明显错误。"""
    for pattern in profile.error_patterns:
        match = pattern.search(output)
        if match:
            line = match.group(0).strip()
            return line or "设备返回错误"
    return None


def _tail(text: str, lines: int = 5) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _has_prompt(text: str, profile: DeviceProfile) -> bool:
    tail = _tail(text)
    return any(pattern.search(tail) for pattern in profile.prompt_patterns)


def _match_incremental(text: str, patterns: Sequence[re.Pattern], start: int) -> Optional[re.Match]:
    segment = text[start:]
    for pattern in patterns:
        match = pattern.search(segment)
        if match:
            return match
    return None


def _match_confirm_rule(
    text: str,
    rules: Sequence[Tuple[re.Pattern, str]],
    start: int,
) -> Optional[Tuple[re.Match, str]]:
    segment = text[start:]
    for pattern, response in rules:
        match = pattern.search(segment)
        if match:
            return match, response
    return None


def execute_device_commands(
    client,
    commands: Sequence[str],
    vendor: Optional[str] = None,
    timeout: int = 30,
    prompt_timeout: float = 8.0,
    quiet_time: float = 0.35,
    disable_paging: bool = True,
    config_mode: bool = False,
    save: bool = False,
) -> Dict[str, object]:
    """
    通过 Paramiko 交互式 shell 执行网络设备命令。

    返回值保持 JSON 友好，便于 CLI 直接输出。
    """
    profile = get_device_profile(vendor)
    commands = expand_command_shortcuts(commands, profile.vendor)
    transcript_parts: List[str] = []
    command_results: List[Dict[str, object]] = []
    errors: List[str] = []

    client.timeout = timeout
    ssh_client = client._get_connection()
    shell = ssh_client.invoke_shell(width=200, height=2000)
    shell.settimeout(1.0)

    cleanup_jump_hosts = bool(getattr(client, "jump_hosts", []))

    def read_until_prompt(stage_timeout: float) -> str:
        start_time = time.monotonic()
        last_data_time = start_time
        handled_offset = 0
        output = ""

        while time.monotonic() - start_time < stage_timeout:
            if shell.recv_ready():
                chunk = shell.recv(65535).decode("utf-8", errors="replace")
                output += chunk
                last_data_time = time.monotonic()

                more_match = _match_incremental(output, profile.more_patterns, handled_offset)
                if more_match:
                    handled_offset = len(output)
                    shell.send(" ")
                    continue

                confirm_match = _match_confirm_rule(output, profile.confirm_rules, handled_offset)
                if confirm_match:
                    _, response = confirm_match
                    handled_offset = len(output)
                    shell.send(response)
                    continue

            if output and _has_prompt(output, profile):
                if time.monotonic() - last_data_time >= quiet_time:
                    return output

            time.sleep(0.1)

        return output

    def run_single_command(command: str, stage_timeout: float) -> Dict[str, object]:
        shell.send(command + "\n")
        output = read_until_prompt(stage_timeout)
        error = detect_error(output, profile)
        return {
            "command": command,
            "success": error is None,
            "error": error,
            "output": output,
        }

    try:
        banner = read_until_prompt(prompt_timeout)
        if banner:
            transcript_parts.append(banner)

        if disable_paging:
            for pre_command in profile.disable_paging_commands:
                pre_result = run_single_command(pre_command, prompt_timeout)
                command_results.append(pre_result)
                transcript_parts.append(pre_result["output"])

        in_config_mode = False
        if config_mode and profile.enter_config_command:
            cfg_result = run_single_command(profile.enter_config_command, prompt_timeout)
            command_results.append(cfg_result)
            transcript_parts.append(cfg_result["output"])
            if not cfg_result["success"]:
                errors.append(f"进入配置模式失败: {cfg_result['error']}")
            else:
                in_config_mode = True

        for command in commands:
            result = run_single_command(command, timeout)
            command_results.append(result)
            transcript_parts.append(result["output"])
            if not result["success"] and result["error"]:
                errors.append(f"{command}: {result['error']}")

        if save and profile.save_command:
            if in_config_mode and not profile.save_in_config_mode and profile.exit_config_command:
                exit_result = run_single_command(profile.exit_config_command, prompt_timeout)
                command_results.append(exit_result)
                transcript_parts.append(exit_result["output"])
                if exit_result["success"]:
                    in_config_mode = False
                elif exit_result["error"]:
                    errors.append(f"退出配置模式失败: {exit_result['error']}")

            save_result = run_single_command(profile.save_command, timeout)
            command_results.append(save_result)
            transcript_parts.append(save_result["output"])
            if not save_result["success"] and save_result["error"]:
                errors.append(f"保存配置失败: {save_result['error']}")

        if in_config_mode and profile.exit_config_command:
            exit_result = run_single_command(profile.exit_config_command, prompt_timeout)
            command_results.append(exit_result)
            transcript_parts.append(exit_result["output"])
            if not exit_result["success"] and exit_result["error"]:
                errors.append(f"退出配置模式失败: {exit_result['error']}")

    finally:
        try:
            shell.close()
        except Exception:
            pass

        if cleanup_jump_hosts:
            try:
                ssh_client.close()
            except Exception:
                pass
            try:
                client._cleanup_jump_connections()
            except Exception:
                pass

    success = not errors and all(item["success"] for item in command_results if item["command"] in commands)
    stderr = "\n".join(errors)
    stdout = "\n".join(part for part in transcript_parts if part)

    return {
        "success": success,
        "exit_code": 0 if success else 1,
        "stdout": stdout,
        "stderr": stderr,
        "mode": "shell",
        "vendor": profile.vendor,
        "commands": command_results,
    }
