import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.image import image_guess_size_from_field_name

_logger = logging.getLogger(__name__)
api_public_fields = {
    "product.product": ["image_1920"],
    "ir.attachment": ["datas", "raw"],
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
    @http.route(
        ["/portal/image/<string:model>/<int:record_id>/<string:field>"],
        type="http",
        auth="public",
    )
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
            stream = self._get_portal_image_stream(
                xmlid=xmlid,
                model=model,
                record_id=record_id,
                field=field,
                filename_field=filename_field,
                filename=filename,
                mimetype=mimetype,
                width=width,
                height=height,
                crop=crop,
                access_token=access_token,
            )
            # Portal images must be publicly cacheable for website <img> tags
            stream.public = True
        except Exception as exc:
            if download:
                raise request.not_found() from exc
            _logger.warning(
                "portal image failed model=%s id=%s field=%s: %s",
                model,
                record_id,
                field,
                exc,
            )
            if (int(width), int(height)) == (0, 0):
                width, height = image_guess_size_from_field_name(field)
            placeholder = request.env.ref("web.image_placeholder").sudo()
            stream = request.env["ir.binary"].sudo()._get_image_stream_from(
                placeholder,
                "raw",
                width=int(width),
                height=int(height),
                crop=crop,
            )
            stream.public = True

        send_file_kwargs = {"as_attachment": download}
        if unique:
            send_file_kwargs["immutable"] = True
            send_file_kwargs["max_age"] = http.STATIC_CACHE_LONG
        if nocache:
            send_file_kwargs["max_age"] = None

        res = stream.get_response(**send_file_kwargs)
        res.headers["Content-Security-Policy"] = "default-src 'none'"
        return res

    def _get_portal_image_stream(
        self,
        xmlid=None,
        model="ir.attachment",
        record_id=None,
        field="raw",
        filename_field="name",
        filename=None,
        mimetype=None,
        width=0,
        height=0,
        crop=False,
        access_token=None,
    ):
        """Build an image stream for portal URLs.

        Attachments always stream from ``raw`` (never ``datas``) to avoid
        base64 decode 500s that break website galleries.
        """
        IrBinary = request.env["ir.binary"].sudo()

        # Dedicated path for gallery attachments linked via product.image_ids
        if model == "ir.attachment" and field in ("datas", "raw"):
            attachment = (
                request.env["ir.attachment"]
                .sudo()
                .browse(int(record_id))
                .exists()
            )
            if not attachment:
                raise UserError("Attachment not found")
            if not (attachment.raw or attachment.datas):
                raise UserError("Attachment has no binary content")
            return IrBinary._get_image_stream_from(
                attachment,
                "raw",
                filename=filename,
                filename_field=filename_field,
                mimetype=mimetype,
                width=int(width),
                height=int(height),
                crop=crop,
            )

        if field not in api_public_fields.get(model, []):
            raise UserError("Field is not publicly available")

        record = IrBinary._find_record(
            xmlid, model, record_id and int(record_id), access_token
        )
        return IrBinary._get_image_stream_from(
            record,
            field,
            filename=filename,
            filename_field=filename_field,
            mimetype=mimetype,
            width=int(width),
            height=int(height),
            crop=crop,
        )
