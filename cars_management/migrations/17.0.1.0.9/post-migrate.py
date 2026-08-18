import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure plate_country_id is filled after rename from mistaken country_id usage."""
    cr.execute("SELECT res_id FROM ir_model_data WHERE module = 'base' AND name = 'sa'")
    row = cr.fetchone()
    if not row:
        return
    sa_id = row[0]
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'fleet_vehicle'
           AND column_name = 'plate_country_id'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE fleet_vehicle
           SET plate_country_id = %s
         WHERE plate_country_id IS NULL
        """,
        (sa_id,),
    )
    _logger.info("Backfilled plate_country_id=SA on %s fleet vehicles", cr.rowcount)
