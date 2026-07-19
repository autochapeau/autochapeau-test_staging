import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.image import image_guess_size_from_field_name

_logger = logging.getLogger(__name__)
api_public_fields = {
    "product.product": ["image_1920"],
    "ir.attachment": ["datas"],
    "res.users": ["image_1920"],
    "fleet.vehicle": ["image_128"],
    "portal.news": ["image_1920"],
    "portal.branch": ["image_1920"],
    "portal.offer": ["image_1920"],
    "portal.aboutus": ["image_1920"],
    "portal.testimony": ["image_1920"],
    "portal.loyalty.program": ["image_1920"],
    "portal.partner": ["image_1920"],
}


class Binary(http.Controller):
    @http.route(["/portal/image/<string:model>/<int:record_id>/<string:field>"], type="http", auth="public")
    def content_image(
        self,
        xmlid=None,
        model="ir.attachment",
        record_id=None,
        field="raw",
        filename_field="name",
        filename=None,
        mimetype=None,
        unique=False,
        download=False,
        width=0,
        height=0,
        crop=False,
        access_token=None,
        nocache=False,
    ):
        try:
            IrBinaryModel = request.env["ir.binary"]
            if field in api_public_fields.get(model, []):
                IrBinaryModel = IrBinaryModel.sudo()
            record = IrBinaryModel._find_record(xmlid, model, record_id and int(record_id), access_token)
            stream = IrBinaryModel._get_image_stream_from(
                record,
                field,
                filename=filename,
                filename_field=filename_field,
                mimetype=mimetype,
                width=int(width),
                height=int(height),
                crop=crop,
            )
            if request.httprequest.args.get("access_token"):
                stream.public = True
        except UserError as exc:
            if download:
                raise request.not_found() from exc
            # Use the ratio of the requested field_name instead of "raw"
            if (int(width), int(height)) == (0, 0):
                width, height = image_guess_size_from_field_name(field)
            record = request.env.ref("web.image_placeholder").sudo()
            stream = IrBinaryModel._get_image_stream_from(
                record,
                "raw",
                width=int(width),
                height=int(height),
                crop=crop,
            )
            stream.public = False

        send_file_kwargs = {"as_attachment": download}
        if unique:
            send_file_kwargs["immutable"] = True
            send_file_kwargs["max_age"] = http.STATIC_CACHE_LONG
        if nocache:
            send_file_kwargs["max_age"] = None

        res = stream.get_response(**send_file_kwargs)
        res.headers["Content-Security-Policy"] = "default-src 'none'"
        return res
