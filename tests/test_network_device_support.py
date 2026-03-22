import os
import sys
import tempfile
import textwrap
import unittest
import json
from io import StringIO
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LIB_DIR = os.path.join(REPO_ROOT, "scripts", "lib")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


from config_v3 import SSHConfigLoaderV3
from network_device import (
    detect_error,
    expand_command_shortcuts,
    get_device_profile,
    is_network_metadata,
    is_network_target,
    split_command_text,
    UnknownShortcutError,
    vendor_from_alias,
    vendor_from_context,
    vendor_from_metadata,
)
from obsidian_credentials import lookup_password
from paramiko_client import ConnectionPool
import ssh_execute


class NetworkDeviceHelperTests(unittest.TestCase):
    def test_split_command_text_supports_delimiter(self):
        commands = split_command_text("show version;;show ip int brief")
        self.assertEqual(commands, ["show version", "show ip int brief"])

    def test_split_command_text_supports_multiline(self):
        commands = split_command_text("display version\n display interface brief \n")
        self.assertEqual(commands, ["display version", "display interface brief"])

    def test_vendor_from_metadata_prefers_explicit_vendor(self):
        vendor = vendor_from_metadata({
            "device_vendor": "ios",
            "tags": ["network", "core-switch"],
        })
        self.assertEqual(vendor, "cisco")

    def test_vendor_from_alias_matches_generic_vendor_markers(self):
        self.assertEqual(vendor_from_alias("hw-access-01"), "huawei")
        self.assertEqual(vendor_from_alias("h3c-floor-07"), "h3c")
        self.assertEqual(vendor_from_alias("edge-fgt-01"), "fortigate")

    def test_vendor_from_context_uses_model_when_metadata_has_no_explicit_vendor(self):
        vendor = vendor_from_context("dist-sw-01", {
            "model": "FutureMatrix S7706",
            "tags": ["network"],
        })
        self.assertEqual(vendor, "huawei")

    def test_is_network_target_detects_alias_without_metadata(self):
        self.assertTrue(is_network_target("core-sw-01", {}))
        self.assertTrue(is_network_target("edge-fw-01", None))
        self.assertFalse(is_network_target("app-web-01", {"tags": ["linux", "web"]}))

    def test_is_network_metadata_detects_tags(self):
        self.assertTrue(is_network_metadata({"tags": ["network", "switch"]}))
        self.assertFalse(is_network_metadata({"tags": ["linux", "web"]}))

    def test_detect_error_for_cisco(self):
        profile = get_device_profile("cisco")
        error = detect_error("% Invalid input detected at '^' marker.", profile)
        self.assertEqual(error, "% Invalid input")

    def test_detect_error_for_huawei(self):
        profile = get_device_profile("huawei")
        error = detect_error("Error: Wrong parameter found at '^' position.", profile)
        self.assertEqual(error, "Error:")

    def test_detect_error_for_fortigate(self):
        profile = get_device_profile("fortigate")
        error = detect_error("Command fail. Return code -61", profile)
        self.assertEqual(error, "Command fail")

    def test_fortigate_profile_does_not_apply_stateful_paging_changes_by_default(self):
        profile = get_device_profile("fortigate")
        self.assertEqual(profile.disable_paging_commands, ())

    def test_more_patterns_do_not_match_normal_output_text(self):
        profile = get_device_profile("generic")
        text = "Need more detail before making a decision."
        self.assertFalse(any(pattern.search(text) for pattern in profile.more_patterns))

    def test_expand_command_shortcuts_for_real_vendor_checks(self):
        self.assertEqual(
            expand_command_shortcuts(["@uptime"], "h3c"),
            ["display version | include uptime"],
        )
        self.assertEqual(
            expand_command_shortcuts(["@status", "@ha"], "fortigate"),
            ["get system status", "get system status | grep HA"],
        )

    def test_unknown_shortcut_raises_clear_error(self):
        with self.assertRaisesRegex(UnknownShortcutError, "@perf"):
            expand_command_shortcuts(["@perf"], "fortigate")


class ProxyJumpParsingTests(unittest.TestCase):
    def test_parse_proxy_jump_supports_alias_and_inline_host(self):
        config_text = textwrap.dedent(
            """
            # ===== bastion-a =====
            # password: jump-pass
            Host bastion-a
                HostName 10.0.0.10
                User jumpuser
                Port 2222

            # ===== edge-switch =====
            # device_vendor: cisco
            Host edge-switch
                HostName 10.10.10.10
                User admin
                ProxyJump bastion-a,ops@10.0.0.20:2200
            """
        ).strip()

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(config_text)

            loader = SSHConfigLoaderV3(config_path=config_path)
            params = loader.get_connection_params("edge-switch")

        self.assertEqual(len(params["jump_hosts"]), 2)
        self.assertEqual(params["jump_hosts"][0]["host"], "10.0.0.10")
        self.assertEqual(params["jump_hosts"][0]["user"], "jumpuser")
        self.assertEqual(params["jump_hosts"][0]["password"], "jump-pass")
        self.assertEqual(params["jump_hosts"][1]["host"], "10.0.0.20")
        self.assertEqual(params["jump_hosts"][1]["user"], "ops")
        self.assertEqual(params["jump_hosts"][1]["port"], 2200)


class SshExecuteCliTests(unittest.TestCase):
    def test_main_returns_json_for_unknown_shortcut(self):
        fake_loader = mock.Mock()
        fake_loader.get_connection_params.return_value = {"metadata": {}}

        with mock.patch("config_v3.SSHConfigLoaderV3", return_value=fake_loader):
            with mock.patch.object(
                ssh_execute,
                "shell_execute",
                side_effect=UnknownShortcutError("未知快捷命令: @perf"),
            ):
                stderr_buffer = StringIO()
                with mock.patch.object(
                    sys,
                    "argv",
                    ["ssh_execute.py", "route", "@perf", "--mode", "shell", "--vendor", "fortigate"],
                ):
                    with redirect_stderr(stderr_buffer):
                        with self.assertRaises(SystemExit) as exit_ctx:
                            ssh_execute.main()

        self.assertEqual(exit_ctx.exception.code, 1)
        error_payload = json.loads(stderr_buffer.getvalue())
        self.assertEqual(error_payload["success"], False)
        self.assertIn("未知快捷命令: @perf", error_payload["stderr"])

    def test_main_exits_cleanly_after_successful_shell_execution(self):
        fake_loader = mock.Mock()
        fake_loader.get_connection_params.return_value = {"metadata": {}}

        result = {
            "success": True,
            "exit_code": 0,
            "stdout": "FortiGate-201F v7.4.7",
            "stderr": "",
            "mode": "shell",
            "vendor": "fortigate",
            "commands": [],
        }

        with mock.patch("config_v3.SSHConfigLoaderV3", return_value=fake_loader):
            with mock.patch.object(ssh_execute, "shell_execute", return_value=result):
                stdout_buffer = StringIO()
                with mock.patch.object(
                    sys,
                    "argv",
                    ["ssh_execute.py", "route", "@status", "--mode", "shell", "--vendor", "fortigate"],
                ):
                    with redirect_stdout(stdout_buffer):
                        with self.assertRaises(SystemExit) as exit_ctx:
                            ssh_execute.main()

        self.assertEqual(exit_ctx.exception.code, 0)
        self.assertIn("FortiGate-201F v7.4.7", stdout_buffer.getvalue())
        self.assertIn('"success": true', stdout_buffer.getvalue().lower())


class ObsidianFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.password_file = os.path.join(self.temp_dir.name, "各项密码.md")
        os.environ["SSH_SKILL_OBSIDIAN_PASSWORD_FILE"] = self.password_file
        os.environ["SSH_SKILL_OBSIDIAN_CONTROLLED_DIR"] = self.temp_dir.name
        self.addCleanup(os.environ.pop, "SSH_SKILL_OBSIDIAN_PASSWORD_FILE", None)
        self.addCleanup(os.environ.pop, "SSH_SKILL_OBSIDIAN_CONTROLLED_DIR", None)

    def write_password_file(self, content: str):
        with open(self.password_file, "w", encoding="utf-8") as handle:
            handle.write(textwrap.dedent(content).strip())

    def test_lookup_password_prefers_ip_match(self):
        self.write_password_file(
            """
            | IP | 主机名 | 设备类型 | 用户名 | 密码 |
            | --- | --- | --- | --- | --- |
            | 10.1.1.1 | firewall | 防火墙 | admin | OBSIDIAN-PW |
            """
        )
        password = lookup_password(hostname="10.1.1.1", alias="route", user="admin")
        self.assertEqual(password, "OBSIDIAN-PW")

    def test_config_loader_uses_obsidian_password_when_config_has_no_password(self):
        self.write_password_file(
            """
            | IP | 主机名 | 设备类型 | 用户名 | 密码 |
            | --- | --- | --- | --- | --- |
            | 10.1.1.2 | core | 核心交换机 | admin | OBSIDIAN-PW |
            """
        )
        config_path = os.path.join(self.temp_dir.name, "config")
        with open(config_path, "w", encoding="utf-8") as handle:
            handle.write(
                textwrap.dedent(
                    """
                    # ===== core =====
                    # description: test core
                    # tags: network
                    Host core
                        HostName 10.1.1.2
                        User admin
                        Port 22
                    """
                ).strip()
            )

        loader = SSHConfigLoaderV3(config_path=config_path)
        params = loader.get_connection_params("core")
        self.assertEqual(params["password"], "OBSIDIAN-PW")
        self.assertEqual(params["password_source"], "obsidian")

    def test_config_loader_keeps_config_password_and_adds_obsidian_fallback(self):
        self.write_password_file(
            """
            | IP | 主机名 | 设备类型 | 用户名 | 密码 |
            | --- | --- | --- | --- | --- |
            | 10.1.1.1 | firewall | 防火墙 | admin | NEW-PW |
            """
        )
        config_path = os.path.join(self.temp_dir.name, "config")
        with open(config_path, "w", encoding="utf-8") as handle:
            handle.write(
                textwrap.dedent(
                    """
                    # ===== route =====
                    # description: test route
                    # tags: network,router
                    # password: OLD-PW
                    Host route
                        HostName 10.1.1.1
                        User admin
                        Port 22
                    """
                ).strip()
            )

        loader = SSHConfigLoaderV3(config_path=config_path)
        params = loader.get_connection_params("route")
        self.assertEqual(params["password"], "OLD-PW")
        self.assertEqual(params["fallback_password"], "NEW-PW")

    def test_lookup_password_is_disabled_without_explicit_env_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SSH_SKILL_OBSIDIAN_PASSWORD_FILE", None)
            os.environ.pop("SSH_SKILL_OBSIDIAN_CONTROLLED_DIR", None)
            password = lookup_password(hostname="10.1.1.1", alias="route", user="admin")
        self.assertIsNone(password)

    def test_connection_pool_retries_with_fallback_password(self):
        pool = ConnectionPool()
        fake_client = mock.Mock()
        auth_exc = Exception("Authentication failed.")
        fake_client.connect.side_effect = [auth_exc, None]
        fake_client.get_transport.return_value = None

        with mock.patch("paramiko_client.paramiko.SSHClient", return_value=fake_client):
            conn = pool.get_connection(
                host="10.1.1.1",
                port=22,
                user="admin",
                password="OLD-PW",
                fallback_password="NEW-PW",
                timeout=10,
            )

        self.assertIs(conn, fake_client)
        self.assertEqual(fake_client.connect.call_count, 2)
        first_password = fake_client.connect.call_args_list[0].kwargs["password"]
        second_password = fake_client.connect.call_args_list[1].kwargs["password"]
        self.assertEqual(first_password, "OLD-PW")
        self.assertEqual(second_password, "NEW-PW")


if __name__ == "__main__":
    unittest.main()
