#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSH命令执行CLI工具 v3.1

默认保持服务器模式；当显式指定网络设备参数，或从元数据识别为
网络设备时，自动切换到交互式 shell 模式。
"""

import sys
import os
import json
import socket
import struct
import argparse
import subprocess

# 添加lib到路径
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_script_dir, 'lib'))


def _send_message(sock, data):
    """发送带长度前缀的 JSON 消息"""
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    header = struct.pack('!I', len(payload))
    sock.sendall(header + payload)


def _recv_message(sock, timeout=None):
    """接收带长度前缀的 JSON 消息"""
    if timeout:
        sock.settimeout(timeout)

    header = b''
    while len(header) < 4:
        chunk = sock.recv(4 - len(header))
        if not chunk:
            raise ConnectionError("连接已关闭")
        header += chunk

    length = struct.unpack('!I', header)[0]
    if length > 10 * 1024 * 1024:
        raise ValueError(f"消息过大: {length} bytes")

    body = b''
    while len(body) < length:
        chunk = sock.recv(min(65536, length - len(body)))
        if not chunk:
            raise ConnectionError("连接已关闭")
        body += chunk

    return json.loads(body.decode('utf-8'))


def try_daemon_execute(alias, command, timeout):
    """尝试通过守护进程执行命令，返回 None 表示守护进程不可用"""
    from ssh_daemon import read_daemon_info

    info = read_daemon_info(alias)
    if not info:
        return None

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout + 5)
        sock.connect(('127.0.0.1', info['port']))
        _send_message(sock, {
            'action': 'execute',
            'command': command,
            'timeout': timeout
        })
        result = _recv_message(sock, timeout=timeout + 5)
        sock.close()
        return result
    except Exception:
        return None


def start_daemon_background(alias):
    """后台启动守护进程"""
    daemon_script = os.path.join(_script_dir, 'ssh_daemon.py')
    try:
        if os.name == 'nt':
            # Windows: 使用 CREATE_NO_WINDOW
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                [sys.executable, daemon_script, 'start', alias],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW
            )
        else:
            subprocess.Popen(
                [sys.executable, daemon_script, 'start', alias],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        # 等待守护进程启动
        import time
        for _ in range(10):
            time.sleep(0.3)
            from ssh_daemon import read_daemon_info
            if read_daemon_info(alias):
                return True
        return False
    except Exception:
        return False


def direct_execute(alias, command, timeout):
    """直连执行命令（智能选择客户端类型）"""
    from config_v3 import SSHConfigLoaderV3

    loader = SSHConfigLoaderV3()

    # 使用智能选择：密钥认证 → NativeSSHClient，密码认证 → ParamikoClient
    client = loader.from_alias(alias)

    # 设置超时
    client.timeout = timeout

    result = client.execute(command)
    return {
        'success': result.success,
        'exit_code': result.exit_code,
        'stdout': result.stdout,
        'stderr': result.stderr
    }


def shell_execute(alias, command_text, timeout, vendor=None, prompt_timeout=8.0,
                  delimiter=';;', disable_paging=True, config_mode=False, save=False):
    """通过 Paramiko 交互式 shell 执行网络设备命令。"""
    from config_v3 import SSHConfigLoaderV3
    from network_device import (
        execute_device_commands,
        split_command_text,
    )

    loader = SSHConfigLoaderV3()
    client = loader.from_alias(alias, prefer_paramiko=True)
    commands = split_command_text(command_text, delimiter=delimiter)

    return execute_device_commands(
        client=client,
        commands=commands,
        vendor=vendor,
        timeout=timeout,
        prompt_timeout=prompt_timeout,
        disable_paging=disable_paging,
        config_mode=config_mode,
        save=save,
    )


def main():
    parser = argparse.ArgumentParser(description='SSH command execution tool v3.1')
    parser.add_argument('alias', help='SSH host alias from ~/.ssh/config')
    parser.add_argument('command', help='Command to execute')
    parser.add_argument('--timeout', type=int, help='Timeout in seconds')
    parser.add_argument('--no-daemon', action='store_true',
                        help='Disable daemon mode, use direct SSH connection')
    parser.add_argument('--mode', choices=['auto', 'exec', 'shell'], default='auto',
                        help='Execution mode: exec for servers, shell for network devices')
    parser.add_argument('--vendor',
                        help='Network vendor profile: generic/cisco/arista/huawei/h3c/juniper')
    parser.add_argument('--prompt-timeout', type=float, default=8.0,
                        help='Interactive prompt wait timeout in seconds')
    parser.add_argument('--delimiter', default=';;',
                        help='Command delimiter for shell mode, default: ;;')
    parser.add_argument('--config-mode', action='store_true',
                        help='Enter vendor config mode before executing commands in shell mode')
    parser.add_argument('--save', action='store_true',
                        help='Save configuration after commands in shell mode')
    parser.add_argument('--no-disable-paging', action='store_true',
                        help='Do not send vendor-specific paging disable commands in shell mode')

    args = parser.parse_args()
    timeout = args.timeout or 30

    try:
        result = None

        # 智能判断是否使用守护进程
        # 守护进程只对密码认证有意义（Paramiko），密钥认证使用原生 SSH 不需要守护进程
        from config_v3 import SSHConfigLoaderV3
        loader = SSHConfigLoaderV3()
        params = loader.get_connection_params(args.alias)
        metadata = params.get('metadata') or {}

        from network_device import is_network_metadata, vendor_from_metadata
        detected_vendor = args.vendor or vendor_from_metadata(metadata)
        auto_shell = args.mode == 'auto' and (bool(args.vendor) or is_network_metadata(metadata))
        use_shell = args.mode == 'shell' or auto_shell

        if use_shell:
            result = shell_execute(
                args.alias,
                args.command,
                timeout=timeout,
                vendor=detected_vendor,
                prompt_timeout=args.prompt_timeout,
                delimiter=args.delimiter,
                disable_paging=not args.no_disable_paging,
                config_mode=args.config_mode,
                save=args.save,
            )
        else:
            has_password = params.get('password') is not None
            use_daemon = has_password and not args.no_daemon  # 只有密码认证才使用守护进程

            if use_daemon:
                # 密码认证：尝试通过守护进程执行
                result = try_daemon_execute(args.alias, args.command, timeout)

                # 守护进程不可用，尝试后台启动
                if result is None:
                    if start_daemon_background(args.alias):
                        result = try_daemon_execute(args.alias, args.command, timeout)

            # 仍然没有结果，使用直连（密钥认证会使用 NativeSSHClient）
            if result is None:
                result = direct_execute(args.alias, args.command, timeout)

        print(json.dumps(result, ensure_ascii=True, indent=2))
        sys.exit(0 if result.get('success') else 1)

    except FileNotFoundError as e:
        print(json.dumps({
            'success': False,
            'exit_code': -1,
            'stdout': '',
            'stderr': f'Config not found: {e}'
        }, ensure_ascii=True, indent=2), file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(json.dumps({
            'success': False,
            'exit_code': -1,
            'stdout': '',
            'stderr': f'Invalid alias: {e}'
        }, ensure_ascii=True, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            'success': False,
            'exit_code': -1,
            'stdout': '',
            'stderr': f'Execution error: {e}'
        }, ensure_ascii=True, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
