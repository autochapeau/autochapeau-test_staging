import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure default Collect Payment methods exist after upgrade (incl. portal labels)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.sale_split_payment.hooks import _ensure_default_collection_methods

    _logger.info("Ensuring sale.collection.method defaults for all companies")
    _ensure_default_collection_methods(env)
