import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Set Saudi Arabia on existing vehicles that have no plate country yet."""
    cr.execute("SELECT res_id FROM ir_model_data WHERE module = 'base' AND name = 'sa'")
    row = cr.fetchone()
    if not row:
        _logger.warning("base.sa country not found; skip fleet.vehicle plate_country backfill")
        return
    sa_id = row[0]

    # Rename legacy column if previous mistaken country_id store exists
    # and plate_country_id is empty.
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'fleet_vehicle'
           AND column_name IN ('plate_country_id', 'country_id')
        """
    )
    cols = {r[0] for r in cr.fetchall()}
    if "plate_country_id" not in cols:
        _logger.warning("plate_country_id column missing; skip backfill")
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
