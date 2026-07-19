import logging

from odoo.api import Environment

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Make original mail template noupdate = True"""

    env = Environment(cr, 1, context={})
    reset_password_data = env["ir.model.data"].search(
        [("module", "=", "auth_signup"), ("name", "=", "reset_password_email")]
    )
    _logger.info("Start: Make original mail template noupdate = True")
    for data in reset_password_data:
        data.write({"noupdate": True})
    _logger.info("Finish: Making original mail template noupdate = True")
