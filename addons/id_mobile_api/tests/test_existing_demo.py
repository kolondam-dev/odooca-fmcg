import hashlib
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..existing_demo import TARGET, protected_snapshot, provision_existing_demo
from ..staging import _provision_records
from .test_read_api import MobileFixture


@tagged("post_install", "-at_install")
class TestExistingDemo(MobileFixture, TransactionCase):
    def setUp(self):
        super().setUp()
        self.files = tempfile.TemporaryDirectory()
        self.addCleanup(self.files.cleanup)
        self.backup = {
            "database": self.env.cr.dbname,
            "target": TARGET,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # Unit gate artifacts only: real pg_dump/archive smoke is separate in CI.
        for key in ("database_dump", "filestore_archive"):
            path = Path(self.files.name) / key
            path.write_bytes(key.encode())
            self.backup[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.runtime = {**TARGET, "PGDATABASE": self.env.cr.dbname}

    def run_provision(self, **changes):
        args = {
            "expected_database": self.env.cr.dbname,
            "opt_in": "PRESERVE_EXISTING_DEMO",
            "backup": self.backup,
            "passwords": ["existing-demo-test-one", "existing-demo-test-two"],
        }
        return provision_existing_demo(self.env, **{**args, **changes})

    def test_exact_target_and_database_opt_in_are_required_before_writes(self):
        before = protected_snapshot(self.env)
        with patch.dict(os.environ, self.runtime):
            for key in TARGET:
                with patch.dict(os.environ, {key: "wrong-target"}), self.assertRaises(AccessError):
                    self.run_provision()
            with self.assertRaises(AccessError):
                self.run_provision(opt_in="YES")
            with self.assertRaises(AccessError):
                self.run_provision(expected_database="different_database")
        self.assertEqual(before, protected_snapshot(self.env))

    def test_backup_scope_hash_and_both_distinct_archives_are_required(self):
        with patch.dict(os.environ, self.runtime):
            for change in (
                {"database": "foreign"},
                {"target": {}},
                {"created_at": "2020-01-01T00:00:00+00:00"},
                {"filestore_archive": self.backup["database_dump"]},
            ):
                with self.assertRaises(AccessError):
                    self.run_provision(backup={**self.backup, **change})
            Path(self.backup["database_dump"]["path"]).write_bytes(b"corrupt")
            with self.assertRaises(AccessError):
                self.run_provision()

    def test_existing_business_rows_are_preserved_on_two_runs(self):
        before = protected_snapshot(self.env)

        def observed(*args, **kwargs):
            self.env.flush_all()
            self.env.cr.execute("SELECT id, to_jsonb(p) FROM res_partner p")
            partners = dict(self.env.cr.fetchall())
            result = _provision_records(*args, **kwargs)
            self.env.flush_all()
            self.env.cr.execute("SELECT id, to_jsonb(p) FROM res_partner p")
            changed = {
                row_id: sorted(key for key in values if values[key] != partners[row_id].get(key))
                for row_id, values in self.env.cr.fetchall()
                if row_id in partners and values != partners[row_id]
            }
            # Field names only; never log any contact values or credentials.
            logging.getLogger(__name__).info("Native partner column changes: %s", changed)
            return result

        with (
            patch.dict(os.environ, self.runtime),
            patch("odoo.addons.id_mobile_api.existing_demo._provision_records", side_effect=observed),
        ):
            first = self.run_provision()
            second = self.run_provision()
        self.assertEqual(first["accounts"], second["accounts"])
        after = protected_snapshot(self.env)
        for model, rows in before.items():
            self.assertTrue(all(after[model].get(row_id) == digest for row_id, digest in rows.items()), model)
        self.assertEqual(self.outlet.name, "API Scheduled Outlet")

    def test_injected_non_fixture_change_rolls_back_the_entire_provision(self):
        original = self.outlet.name

        def mutated(*args, **kwargs):
            result = _provision_records(*args, **kwargs)
            self.outlet.name = "Unexpected existing customer mutation"
            return result

        with (
            patch.dict(os.environ, self.runtime),
            patch("odoo.addons.id_mobile_api.existing_demo._provision_records", side_effect=mutated),
            self.assertRaises(ValidationError),
        ):
            self.run_provision()
        self.assertEqual(self.outlet.name, original)
        self.assertFalse(self.env["res.users"].search([("login", "=", "staging.capture.1")]))

    def test_existing_login_is_not_taken_over(self):
        self.other.login = "staging.capture.1"
        before = protected_snapshot(self.env)
        with patch.dict(os.environ, self.runtime), self.assertRaises(ValidationError):
            self.run_provision()
        self.assertEqual(before, protected_snapshot(self.env))

    def test_unexpected_operator_group_change_is_rolled_back(self):
        group = self.env["res.groups"].create({"name": "Unexpected operator privilege"})

        def mutated(*args, **kwargs):
            result = _provision_records(*args, **kwargs)
            self.env.user.group_ids = [Command.link(group.id)]
            return result

        with (
            patch.dict(os.environ, self.runtime),
            patch("odoo.addons.id_mobile_api.existing_demo._provision_records", side_effect=mutated),
            self.assertRaises(ValidationError),
        ):
            self.run_provision()
        self.assertNotIn(group, self.env.user.group_ids)
