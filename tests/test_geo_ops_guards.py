"""Regression tests for geo ops guards and dataset set verification.

The archive tests drive ``_documents()`` and ``main()`` with a fake Odoo
environment, so reservations and moves without picking are proven to block
before any write or commit happens.

Run: python -m unittest tests.test_geo_ops_guards -v
"""

import contextlib
import io
import os
import unittest
from unittest import mock

from scripts.ops import archive_staging_company as archive
from scripts.ops import verify_geo_backfill as verify


class _FakeRecord:
    def __init__(self, **values):
        self.__dict__.update(values)


class _FakeRecordset:
    def __init__(self, model, records):
        self._model = model
        self._records = list(records)

    def __iter__(self):
        return iter(self._records)

    def __len__(self):
        return len(self._records)

    def __bool__(self):
        return bool(self._records)

    def filtered(self, predicate):
        return _FakeRecordset(self._model, [record for record in self._records if predicate(record)])

    def sudo(self):
        return self

    def with_context(self, **_kwargs):
        return self

    def search(self, domain):
        return self._model.search(domain)

    def search_count(self, domain):
        return self._model.search_count(domain)

    def write(self, values):
        self._model.writes.append(([record.id for record in self._records], dict(values)))
        for record in self._records:
            for key, value in values.items():
                setattr(record, key, value)
        return True

    @property
    def id(self):
        return self._records[0].id

    @property
    def name(self):
        return self._records[0].name

    @property
    def env(self):
        return self._model.env


class _FakeModel:
    def __init__(self, name, records=(), counts=None):
        self.env = None
        self.name = name
        self.records = list(records)
        self.counts = dict(counts or {})
        self.writes = []

    def sudo(self):
        return self

    def with_context(self, **_kwargs):
        return self

    def search(self, domain):
        records = self.records
        if self.name == "res.company" and ("active", "=", True) in domain:
            records = [record for record in records if getattr(record, "active", True)]
        return _FakeRecordset(self, records)

    def search_count(self, domain):
        if self.name == "res.company":
            return len([record for record in self.records if getattr(record, "active", True)])
        return self.counts.get(self.name, 0)


class _FakeEnv:
    def __init__(self, models):
        self.registry = models
        self.committed = False
        self.flushed = False
        self.cr = self
        for model in models.values():
            model.env = self

    def __getitem__(self, name):
        return self.registry[name]

    def flush_all(self):
        self.flushed = True

    def commit(self):
        self.committed = True


def _build_env(counts=None, logins=("staging.capture.1", "staging.capture.2")):
    counts = counts or {}
    target = _FakeRecord(id=2, name=archive.TARGET_NAME, active=True)
    other = _FakeRecord(id=1, name="PT Manado Distribusi Utama", active=True)
    users = [
        _FakeRecord(id=10 + index, login=login, active=True, company_id=target.id)
        for index, login in enumerate(logins)
    ]
    models = {
        "res.company": _FakeModel("res.company", [other, target]),
        "res.users": _FakeModel("res.users", users),
    }
    for model_name in archive.DOCUMENT_MODELS:
        models[model_name] = _FakeModel(model_name, [], {model_name: counts.get(model_name, 0)})
    models[archive.QUANT_MODEL] = _FakeModel(
        archive.QUANT_MODEL, [], {archive.QUANT_MODEL: counts.get(archive.QUANT_MODEL, 0)}
    )
    return _FakeEnv(models), target, users


class ArchiveGuardTests(unittest.TestCase):
    def test_no_activity_does_not_block(self):
        counts = {"account.move": 0, "stock.move": 0, "stock.quant": 0}
        self.assertEqual(archive.blocking_documents(counts), {})

    def test_any_stock_activity_blocks(self):
        for model in ("stock.move", "stock.move.line", "stock.scrap", "mrp.production", "stock.quant"):
            with self.subTest(model=model):
                self.assertEqual(archive.blocking_documents({model: 1}), {model: 1})

    def test_quant_reservation_counts_as_activity(self):
        # The quant counter uses quantity OR reserved_quantity, so a pure
        # reservation yields a non-zero count and must block archiving.
        self.assertTrue(archive.blocking_documents({"stock.quant": 2}))

    def test_test_logins_are_accepted(self):
        self.assertEqual(archive.unexpected_logins(["staging.capture.1", "staging.capture.2"]), [])

    def test_non_test_login_is_reported(self):
        self.assertEqual(archive.unexpected_logins(["staging.capture.1", "admin"]), ["admin"])


class ArchiveMainTests(unittest.TestCase):
    """Drive main() end to end against a fake environment."""

    def _run(self, env, confirm=True, allow_users=False):
        archive.env = env
        self.addCleanup(lambda: archive.__dict__.pop("env", None))
        settings = {"ARCHIVE_COMPANY_ALLOW_USERS": "yes" if allow_users else ""}
        if confirm:
            settings["ARCHIVE_COMPANY_CONFIRM"] = "yes"
        with mock.patch.dict(os.environ, settings, clear=False), contextlib.redirect_stdout(io.StringIO()):
            archive.main()

    def test_documents_reads_every_stock_model(self):
        counts = {"stock.move": 1, "stock.move.line": 2, "stock.scrap": 3, "mrp.production": 4, "stock.quant": 5}
        env, target, _users = _build_env(counts)
        archive.env = env
        self.addCleanup(lambda: archive.__dict__.pop("env", None))
        documents = archive._documents(env["res.company"].search([]).filtered(lambda r: r.id == target.id))
        for model_name in ("stock.move", "stock.move.line", "stock.scrap", "mrp.production", "stock.quant"):
            with self.subTest(model=model_name):
                self.assertEqual(documents[model_name], counts[model_name])

    def test_reservation_blocks_before_write(self):
        env, target, _users = _build_env({"stock.quant": 1})
        with self.assertRaises(RuntimeError):
            self._run(env)
        self.assertTrue(target.active)
        self.assertEqual(env["res.company"].writes, [])
        self.assertFalse(env.committed)

    def test_move_without_picking_blocks_before_write(self):
        env, target, _users = _build_env({"stock.move": 1})
        with self.assertRaises(RuntimeError):
            self._run(env)
        self.assertTrue(target.active)
        self.assertEqual(env["res.company"].writes, [])
        self.assertFalse(env.committed)

    def test_move_line_blocks_before_write(self):
        env, target, _users = _build_env({"stock.move.line": 1})
        with self.assertRaises(RuntimeError):
            self._run(env)
        self.assertTrue(target.active)
        self.assertFalse(env.committed)

    def test_non_test_login_blocks_before_write(self):
        env, target, _users = _build_env({}, logins=("staging.capture.1", "admin"))
        with self.assertRaises(RuntimeError):
            self._run(env)
        self.assertTrue(target.active)
        self.assertFalse(env.committed)

    def test_clean_target_archives_users_and_commits(self):
        env, target, users = _build_env({})
        self._run(env)
        self.assertFalse(target.active)
        self.assertTrue(all(not user.active for user in users))
        self.assertTrue(env.committed)
        self.assertEqual(env["res.company"].writes[0][1], {"active": False})

    def test_dry_run_never_writes(self):
        env, target, users = _build_env({})
        self._run(env, confirm=False)
        self.assertTrue(target.active)
        self.assertTrue(all(user.active for user in users))
        self.assertFalse(env.committed)
        self.assertEqual(env["res.company"].writes, [])


class DatasetSetTests(unittest.TestCase):
    dataset = {"71.71.01", "71.71.02", "71.71.03"}

    def test_identical_set_passes(self):
        ok, detail = verify.set_ok(self.dataset, {code: 1 for code in self.dataset})
        self.assertTrue(ok)
        self.assertEqual(detail["missing"], [])
        self.assertEqual(detail["extra"], [])
        self.assertEqual(detail["rows"], 3)

    def test_swapped_code_fails_even_with_same_count(self):
        counts = {"71.71.01": 1, "71.71.02": 1, "71.99.99": 1}
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["rows"], 3)
        self.assertEqual(detail["missing"], ["71.71.03"])
        self.assertEqual(detail["extra"], ["71.99.99"])

    def test_fabricated_code_with_same_row_count_fails(self):
        counts = {code: 1 for code in self.dataset}
        counts["71.00.00"] = 1
        del counts["71.71.02"]
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["missing"], ["71.71.02"])
        self.assertEqual(detail["extra"], ["71.00.00"])

    def test_duplicate_code_fails(self):
        counts = {code: 1 for code in self.dataset}
        counts["71.71.01"] = 2
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["duplicates"], ["71.71.01"])

    def test_missing_code_fails(self):
        counts = {"71.71.01": 1, "71.71.02": 1}
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["missing"], ["71.71.03"])

    def test_dataset_expectations_match_acceptance(self):
        self.assertEqual(verify.EXPECTED, {"city": 15, "district": 171, "village": 1839})


if __name__ == "__main__":
    unittest.main()
