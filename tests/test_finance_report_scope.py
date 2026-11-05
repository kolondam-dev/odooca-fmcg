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


if __name__ == "__main__":
    unittest.main()
