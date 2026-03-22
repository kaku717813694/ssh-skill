import os
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LIB_DIR = os.path.join(REPO_ROOT, "scripts", "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


from config_v3 import SSHConfigLoaderV3
from network_device import (
    detect_error,
    expand_command_shortcuts,
    get_device_profile,
    is_network_metadata,
    is_network_target,
    split_command_text,
    vendor_from_alias,
    vendor_from_context,
    vendor_from_metadata,
)


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

    def test_expand_command_shortcuts_for_real_vendor_checks(self):
        self.assertEqual(
            expand_command_shortcuts(["@uptime"], "h3c"),
            ["display version | include uptime"],
        )
        self.assertEqual(
            expand_command_shortcuts(["@status", "@ha"], "fortigate"),
            ["get system status", "get system ha status"],
        )


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


if __name__ == "__main__":
    unittest.main()
