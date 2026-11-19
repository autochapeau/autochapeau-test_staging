"""Run isolated TEST CLI checks without external Python networking."""
import socket
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
from odoo.cli import main
main()
