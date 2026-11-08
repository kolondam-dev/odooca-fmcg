"""Profile planning/attestation unit contracts, not native installation proof."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("activation", ROOT / "scripts/ops/finance_activation.py")
activation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(activation)


class Params(dict):
    def get_param(self, key):
        return self.get(key)

    def set_param(self, key, value):
        self[key] = value


class Environment:
    su = True

    def __init__(self):
        self.params = Params()
        self.modules = [SimpleNamespace(name=name, state="installed", latest_version="19.0.1.0.0")
                        for name in activation.MODULES]
        for module in self.modules:
            module.dependencies_id = SimpleNamespace(mapped=lambda field: [])

    def __getitem__(self, model):
        if model == "ir.module.module":
            return SimpleNamespace(search=lambda domain: [
                module for module in self.modules if module.name in domain[0][2]
            ])
        if model == "ir.config_parameter":
            return self.params
        raise AssertionError(model)


class ActivationTests(unittest.TestCase):
    def test_transitive_dependency_state_and_version_are_part_of_marker(self):
        env = Environment()
        env.modules[0].dependencies_id = SimpleNamespace(mapped=lambda field: ["dependency"])
        dependency = SimpleNamespace(name="dependency", state="uninstalled", latest_version="19.0.1.0.0",
                                     dependencies_id=SimpleNamespace(mapped=lambda field: [activation.MODULES[0]]))
        env.modules.append(dependency)
        with self.assertRaisesRegex(RuntimeError, "incompletely installed"):
            activation.attest(env)
        dependency.state = "installed"
        activation.attest(env)
        dependency.latest_version = "19.0.2.0.0"
        with self.assertRaisesRegex(RuntimeError, "version drift"):
            activation.attest(env)

    def test_plan_never_writes_and_refuses_unknown_missing_profile(self):
        env = Environment()
        self.assertEqual(activation.plan(env)["profile"], activation.PROFILE)
        self.assertFalse(env.params)
        with self.assertRaises(ValueError):
            activation.plan(env, "all")
        env.modules.pop()
        with self.assertRaisesRegex(RuntimeError, "sources missing"):
            activation.plan(env)

    def test_attestation_requires_complete_registry_superuser_and_no_drift(self):
        env = Environment()
        env.su = False
        with self.assertRaises(PermissionError):
            activation.attest(env)
        env.su = True
        env.modules[0].state = "uninstalled"
        with self.assertRaisesRegex(RuntimeError, "incompletely installed"):
            activation.attest(env)
        self.assertFalse(env.params)
        env.modules[0].state = "installed"
        self.assertEqual(activation.attest(env)["result"], "RECORDED")
        before = dict(env.params)
        self.assertEqual(activation.attest(env)["result"], "UNCHANGED")
        self.assertEqual(env.params, before)
        env.modules[0].latest_version = "19.0.2.0.0"
        with self.assertRaisesRegex(RuntimeError, "version drift"):
            activation.attest(env)
        self.assertEqual(env.params, before)


if __name__ == "__main__":
    unittest.main()
