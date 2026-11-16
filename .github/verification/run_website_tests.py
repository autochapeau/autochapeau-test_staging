"""Run website acceptance regressions against TEST ORM, always rolling back."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import types

from odoo import tools
from odoo.tests import loader

assert env.cr.dbname == "autochapeau_prod_test"
root = Path(os.environ["WEBSITE_VERIFICATION_ROOT"])
package_name = "odoo.addons.portal_api.tests"
package = types.ModuleType(package_name)
package.__path__ = [str(root)]
package.__spec__ = importlib.util.spec_from_loader(package_name, loader=None, is_package=True)
sys.modules[package_name] = package
name = package_name + ".test_website_release"
spec = importlib.util.spec_from_file_location(name, root / "test_website_release.py")
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)
package.test_website_release = module
tools.config["test_tags"] = "website_release"
suite = loader.make_suite(["portal_api"], position="post_install")
original_connect = socket.socket.connect
def no_external_network(*args, **kwargs):
    raise RuntimeError("Website regression: external network disabled")
socket.socket.connect = no_external_network
try:
    result = loader.run_suite(suite)
finally:
    socket.socket.connect = original_connect
    env.cr.rollback()
summary = {"tests": result.testsRun, "failures": result.failures_count,
           "errors": result.errors_count, "skipped": result.skipped}
print("WEBSITE_TEST_REGRESSION=" + json.dumps(summary, sort_keys=True))
assert result.testsRun >= 13 and not any((result.failures_count, result.errors_count, result.skipped)), summary
