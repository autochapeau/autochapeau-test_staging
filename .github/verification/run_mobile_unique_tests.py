"""Run mobile regression tests with rollback and external network disabled."""
import importlib
import json
import socket

from odoo import tools
from odoo.tests import loader

importlib.import_module("odoo.addons.partner_management.tests.test_mobile_unique")
tools.config["test_tags"] = "partner_mobile_unique"
suite = loader.make_suite(["partner_management"], position="post_install")
original_connect = socket.socket.connect


def no_network(*args, **kwargs):
    raise RuntimeError("Mobile regression tests cannot contact external services")


socket.socket.connect = no_network
try:
    result = loader.run_suite(suite)
finally:
    socket.socket.connect = original_connect
    env.cr.rollback()
summary = {"database": env.cr.dbname, "tests": result.testsRun,
           "failures": result.failures_count, "errors": result.errors_count}
print("MODULE_UNIQUE_TESTS=" + json.dumps(summary, sort_keys=True))
assert result.testsRun >= 9 and not result.failures_count and not result.errors_count, summary
