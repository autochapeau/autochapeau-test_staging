from pathlib import Path

from odoo import http
from odoo.http import request
from odoo.modules.module import get_module_resource


class MaintenanceGuide(http.Controller):
    @http.route('/maintenance-guide', type='http', auth='user', methods=['GET'])
    def maintenance_guide(self, **kwargs):
        path = get_module_resource('order_maintenance', 'static', 'guide', 'index.html')
        return request.make_response(Path(path).read_text(encoding='utf-8'), headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
        ])
