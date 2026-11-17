"""Regresiones de configuración, auditoría y gestión de peers (sin daemon)."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wg_audit", ROOT / "scripts/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def environment():
    return dict(line.split("=", 1) for line in (ROOT / "env.example").read_text().splitlines()
                if line and not line.startswith("#"))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "env"
        self.config = self.runtime / "config"
        self.config.mkdir(parents=True)
        self.patches = patch.multiple(audit, ROOT=self.root, RUNTIME=self.runtime,
                                     CONFIG=self.config, ENV_FILE=self.runtime / ".env",
                                     AUDITS=self.runtime / "audits")
        self.patches.start()
        self.addCleanup(self.patches.stop)
        audit.CHECKS.clear()
        self.env = environment()

    def result(self, code):
        return next(c["status"] for c in audit.CHECKS if c["code"] == code)

    def test_default_environment_valid(self):
        audit.validate_env(self.env)
        self.assertFalse(any(c["status"] == "FAIL" for c in audit.CHECKS))

    def test_unsupported_subnets_rejected(self):
        for net in ("10.67.47.8", "10.67.47.0/24", "10.67.47.0/16", "8.8.8.0", "::1"):
            with self.subTest(net=net):
                audit.CHECKS.clear()
                audit.validate_env(dict(self.env, INTERNAL_SUBNET=net))
                self.assertEqual(self.result("TUNNEL_SUBNET"), "FAIL")

    def test_numeric_empty_or_duplicate_peers_rejected(self):
        for peers in ("3", "android,2", "android,", "android,android", "android,lap_top"):
            with self.subTest(peers=peers):
                audit.CHECKS.clear()
                audit.validate_env(dict(self.env, PEERS=peers))
                self.assertEqual(self.result("PEER_FORMAT"), "FAIL")

    def test_invalid_ids_timezone_dns_endpoint(self):
        for key, value, code in (("PUID", "0", "PUID"), ("PGID", "abc", "PGID"),
                                 ("TZ", "Mars/Olympus", "TIMEZONE"),
                                 ("PEERDNS", "invalid", "PEER_DNS"),
                                 ("SERVERURL", "::1", "ENDPOINT")):
            with self.subTest(key=key):
                audit.CHECKS.clear()
                audit.validate_env(dict(self.env, **{key: value}))
                self.assertEqual(self.result(code), "FAIL")

    def test_duplicate_and_interpolated_env_fail(self):
        audit.ENV_FILE.write_text("PEERS=android\nPEERS=laptop\nPUID=${UID}\n")
        audit.env_read()
        self.assertEqual(self.result("ENV_DUPLICATE"), "FAIL")
        self.assertEqual(self.result("ENV_LITERAL"), "FAIL")

    def test_missing_env_report_returns_failure(self):
        with patch.object(sys, "argv", ["audit.py", "post", "--fail-on-error"]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                audit.main()
        self.assertEqual(caught.exception.code, 2)
        reports = list(audit.AUDITS.glob("*.json"))
        self.assertEqual(len(reports), 1)
        self.assertGreater(json.loads(reports[0].read_text())["summary"]["FAIL"], 0)
        self.assertEqual(stat.S_IMODE(reports[0].stat().st_mode), 0o600)

    def container(self):
        return {"State": {"Running": True, "Health": {"Status": "healthy"}},
                "Config": {"Env": [f"{k}={v}" for k, v in self.env.items()]}}

    def test_empty_interface_output_is_failure(self):
        with patch.object(audit, "run", return_value=(0, "", "")):
            audit.runtime(self.env, audit.validate_env(self.env), self.container())
        self.assertEqual(self.result("WG_INTERFACE"), "FAIL")

    def test_custom_external_port_still_listens_internally_51820(self):
        self.env["SERVERPORT"] = "51920"
        for peer in ("android", "laptop"):
            folder = self.config / f"peer_{peer}"
            folder.mkdir()
            (folder / f"publickey-peer_{peer}").write_text(f"public-{peer}")
        def execute(command, **kwargs):
            outputs = {"interfaces": "wg0", "listen-port": "51820",
                       "peers": "public-android\npublic-laptop", "latest-handshakes": ""}
            return 0, outputs.get(command[-1], "1"), ""
        with patch.object(audit, "run", side_effect=execute):
            audit.runtime(self.env, audit.validate_env(self.env), self.container())
        self.assertEqual(self.result("WG_LISTEN"), "PASS")
        self.assertEqual(self.result("ACTIVE_PEERS"), "PASS")

    def test_stale_container_environment_is_failure(self):
        obj = self.container()
        self.env["PEERS"] += ",tablet"
        with patch.object(audit, "run", return_value=(0, "", "")):
            audit.runtime(self.env, audit.validate_env(self.env), obj)
        self.assertEqual(self.result("ENV_APPLIED"), "FAIL")

    def test_unhealthy_container_is_failure(self):
        obj = self.container()
        obj["State"]["Health"]["Status"] = "unhealthy"
        with patch.object(audit, "run", return_value=(0, "", "")):
            audit.runtime(self.env, audit.validate_env(self.env), obj)
        self.assertEqual(self.result("HEALTH"), "FAIL")

    def test_wrong_project_container_is_not_audited_as_ours(self):
        with patch.object(audit, "run", return_value=(0, json.dumps([self.container()]), "")):
            self.assertIsNone(audit.inspect_container())
        self.assertEqual(self.result("CONTAINER_PROJECT"), "FAIL")

    def test_removed_runtime_peer_is_failure(self):
        with patch.object(audit, "run", side_effect=lambda cmd, **kw: (0, "wg0" if cmd[-1] == "interfaces" else "", "")):
            audit.runtime(self.env, audit.validate_env(self.env), self.container())
        self.assertEqual(self.result("ACTIVE_PEERS"), "FAIL")


class PeerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = Path(self.tmp.name) / ".env"
        self.env.write_text("PEERS=android,laptop\nSERVERPORT=51820\n")

    def edit(self, cmd, peer):
        return subprocess.run([sys.executable, str(ROOT / "scripts/peers.py"), cmd, peer, str(self.env)],
                              capture_output=True, text=True)

    def test_add_revoke_and_permissions(self):
        self.assertEqual(self.edit("add-peer", "tablet").returncode, 0)
        self.assertIn("PEERS=android,laptop,tablet", self.env.read_text())
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)
        self.assertEqual(self.edit("revoke-peer", "tablet").returncode, 0)
        self.assertIn("PEERS=android,laptop\n", self.env.read_text())

    def test_invalid_duplicate_or_unknown_does_not_change_env(self):
        original = self.env.read_bytes()
        for cmd, peer in (("add-peer", "2"), ("add-peer", "android"),
                          ("add-peer", "../key"), ("revoke-peer", "absent")):
            with self.subTest(cmd=cmd, peer=peer):
                self.assertNotEqual(self.edit(cmd, peer).returncode, 0)
                self.assertEqual(self.env.read_bytes(), original)

    def test_last_peer_cannot_be_revoked(self):
        self.env.write_text("PEERS=android\n")
        self.assertNotEqual(self.edit("revoke-peer", "android").returncode, 0)
        self.assertEqual(self.env.read_text(), "PEERS=android\n")

    def test_capacity_enforced_before_modifying_env(self):
        content = "PEERS=" + ",".join(f"peer{i}" for i in range(250)) + "\n"
        self.env.write_text(content)
        self.assertNotEqual(self.edit("add-peer", "extra").returncode, 0)
        self.assertEqual(self.env.read_text(), content)


if __name__ == "__main__":
    unittest.main()
