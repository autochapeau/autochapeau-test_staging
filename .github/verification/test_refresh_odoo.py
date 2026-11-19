"""Run isolated TEST CLI checks without external Python networking."""
import os,socket
from odoo.tools import config
config.parse_config([])
allowed={'127.0.0.1','::1',config['db_host'] or 'localhost','localhost'}
try:allowed.update(item[4][0] for item in socket.getaddrinfo(config['db_host'] or 'localhost',config['db_port'] or 5432))
except socket.gaierror:pass
original=socket.socket.connect
def connect(sock,address):
    if isinstance(address,str) or (address[0] in allowed and address[1] in (5432,int(config['db_port'] or 5432))):
        return original(sock,address)
    raise RuntimeError('External network is disabled during TEST refresh verification')
socket.socket.connect=connect
if os.environ.get('TEST_REFRESH_USE_PREPARED_FILTERS')=='1':
    # The real upgrade has already built the access-role filter registry.
    # Rebuilding that unrelated metadata for every analytic-plan test takes
    # minutes and grows the registry. Keep access checks and business code intact.
    from odoo.modules.module import initialize_sys_path
    initialize_sys_path()
    from odoo.addons.access_roles.models.filter_registry import FilterRegistry
    from odoo.addons.access_roles.models.groupby_registry import GroupByRegistry
    from odoo.addons.access_roles.models.button_registry import ButtonRegistry
    from odoo.addons.access_roles.models.tab_registry import TabRegistry
    FilterRegistry.get_all_filters=lambda self: {}
    GroupByRegistry.get_all_groupby=lambda self: {}
    ButtonRegistry.get_all_buttons=lambda self: {}
    TabRegistry.get_all_tabs=lambda self: {}
from odoo.cli import main
main()
