"""Exercise the production scope guard without importing the Odoo runtime."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class Denied(Exception):
    pass


SOURCE = Path(__file__).parents[1] / "addons/id_finance_reporting/models/trial_balance.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
METHOD = next(
    node for node in ast.walk(TREE) if isinstance(node, ast.FunctionDef) and node.name == "_check_finance_scope"
)
NAMESPACE = {"AccessError": Denied, "_": lambda message: message}
exec(compile(ast.Module(body=[METHOD], type_ignores=[]), str(SOURCE), "exec"), NAMESPACE)
guard = NAMESPACE["_check_finance_scope"]


def subject(groups=(), active=(1,), authorized=(1,), superuser=False):
    return SimpleNamespace(env=SimpleNamespace(
        su=superuser, companies=SimpleNamespace(ids=list(active)),
        user=SimpleNamespace(has_group=lambda name: name in groups, company_ids=SimpleNamespace(ids=list(authorized))),
    ))


class FinanceScopeTests(unittest.TestCase):
    def test_reader_accountant_and_manager_allowed(self):
        for role in ("readonly", "user", "manager"):
            guard(subject(groups=[f"account.group_account_{role}"]), 1)

    def test_internal_sales_or_driver_without_accounting_denied(self):
        for groups in (
            [], ["base.group_user"], ["sales_team.group_sale_salesman"], ["id_mobile_api.group_mobile_evidence"],
        ):
            with self.assertRaisesRegex(Denied, "accounting role"):
                guard(subject(groups=groups), 1)

    def test_company_missing_inactive_and_unauthorized_denied(self):
        reader = ["account.group_account_readonly"]
        for instance, company in (
            (subject(groups=reader), False),
            (subject(groups=reader), 2),
            (subject(groups=reader, active=(1, 2), authorized=(1,)), 2),
        ):
            with self.assertRaisesRegex(Denied, "active accounting context"):
                guard(instance, company)

    def test_superuser_still_requires_explicit_active_company(self):
        guard(subject(superuser=True), 1)
        with self.assertRaisesRegex(Denied, "active accounting context"):
            guard(subject(superuser=True), False)

    def test_foreign_journal_and_account_filters_denied(self):
        filter_method = next(
            node for node in ast.walk(TREE)
            if isinstance(node, ast.FunctionDef) and node.name == "_check_filter_company"
        )
        ns = {"AccessError": Denied, "_": lambda message: message}
        exec(compile(ast.Module(body=[filter_method], type_ignores=[]), str(SOURCE), "exec"), ns)
        check_filter = ns["_check_filter_company"]

        def filter_subject(journals=(), accounts=()):
            j_map = {j.id: j for j in journals}
            a_map = {a.id: a for a in accounts}
            return SimpleNamespace(env={
                "account.journal": SimpleNamespace(
                    with_context=lambda **_kw: SimpleNamespace(browse=lambda ids: [j_map[i] for i in ids]),
                ),
                "account.account": SimpleNamespace(
                    with_context=lambda **_kw: SimpleNamespace(browse=lambda ids: [a_map[i] for i in ids]),
                ),
            })

        j_ok = SimpleNamespace(id=10, company_id=SimpleNamespace(id=1))
        j_bad = SimpleNamespace(id=20, company_id=SimpleNamespace(id=2))
        a_ok = SimpleNamespace(id=100, company_ids=SimpleNamespace(ids=[1]))
        a_bad = SimpleNamespace(id=200, company_ids=SimpleNamespace(ids=[2]))
        instance = filter_subject([j_ok, j_bad], [a_ok, a_bad])
        check_filter(instance, 1, [10], [100])
        with self.assertRaisesRegex(Denied, "journal belongs to another company"):
            check_filter(instance, 1, [20], [100])
        with self.assertRaisesRegex(Denied, "account belongs to another company"):
            check_filter(instance, 1, [10], [200])



if __name__ == "__main__":
    unittest.main()
