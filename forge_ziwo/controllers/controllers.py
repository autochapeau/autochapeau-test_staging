# -*- coding: utf-8 -*-
from odoo import http
import base64


class ForgeZiwo(http.Controller):

    @http.route('/forge_ziwo/ziwo_component/', auth='public')
    def list(self, **kw):
        return http.request.render('forge_ziwo.ziwo_web_component', {})