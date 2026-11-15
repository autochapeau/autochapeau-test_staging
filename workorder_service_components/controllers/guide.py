from pathlib import Path

from odoo import http
from odoo.http import request
from odoo.modules.module import get_module_resource


class ServiceMaterialGuide(http.Controller):
    @http.route('/service-materials-guide', type='http', auth='user', methods=['GET'])
    def service_materials_guide(self, **kwargs):
        path = get_module_resource('workorder_service_components', 'static', 'guide', 'index.html')
        return request.make_response(Path(path).read_text(encoding='utf-8'), headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
        ])
