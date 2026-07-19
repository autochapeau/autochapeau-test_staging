import functools
import json
from datetime import date

import pytz

from odoo.http import Response, request
from odoo.tools import format_duration
from odoo.tools.misc import frozendict


def find_missing_keys(dictionary, key_list):
    return [key for key in key_list if key not in dictionary]


def find_empty_values(dictionary, key_list):
    return [key for key in key_list if key in dictionary and not dictionary[key]]


def check_params(params, required_keys):
    missing_keys = find_missing_keys(params, required_keys)
    empty_keys = find_empty_values(params, required_keys)
    if missing_keys or empty_keys:
        errors = []
        for key in missing_keys:
            errors.append({"field": key, "message": f"{key} missing"})
        for key in empty_keys:
            errors.append({"field": key, "message": f"Empty field {key} "})
        return {"message": "The request data contains invalid " "fields or fails validation", "errors": errors}
    return False


def authorization_required(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        is_json_route = bool(getattr(request, "endpoint", None)
                             and request.endpoint.routing.get("type") == "json")

        def _auth_error(status, message):
            if is_json_route:
                return {"code": status, "message": message}
            return Response(
                json.dumps({"error": message}),
                headers=[("Content-Type", "application/json")],
                status=status,
            )

        # check the authorization header
        authorization_header = (request.httprequest.headers.get(
            "Authorization") or "").strip()
        access_token = False
        if authorization_header:
            parts = authorization_header.split()
            access_token = parts[-1] if parts else False
        if not access_token:
            return _auth_error(400, "Authorization header missing")
        # check if the api key is correct
        user_id = request.env["res.users.apikeys"]._check_credentials(
            scope="api", key=access_token)
        if not user_id:
            return _auth_error(401, "Access token invalid")
        # take the identity of the API key user
        request.update_env(user=user_id)
        # switch to the user context
        request.env.context = frozendict(
            {**request.env.context, **request.env.user.sudo().context_get()})
        return func(*args, **kwargs)

    return wrapper


def check_request_body(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Check the request body content
        if not request.httprequest.data:
            return Response(
                json.dumps({"error": "Request body content missing"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )
        # check the data should refers to JSON Payload
        try:
            json.loads(request.httprequest.data)
        except Exception as e:
            return Response(
                json.dumps(
                    {"message": f"Payload validation error {str(e)} ", "errors": []}),
                headers=[("Content-Type", "application/json")],
                status=422,
            )
        return func(*args, **kwargs)

    return wrapper


def with_lang(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with_specific_lang = "en_US"
        if request.httprequest.args.get("lang", False) == "ar":
            with_specific_lang = "ar_001"
        ctx = request.env.context.copy()
        ctx["lang"] = with_specific_lang
        request.update_env(context=ctx)
        return func(*args, **kwargs)

    return wrapper


def make_response(code, message=False):
    message = format_message(message)
    return Response(json.dumps(message), headers=[("Content-Type", "application/json")], status=code)


def make_json_response(code, message=False):
    message = format_message(message)
    if isinstance(message, dict):
        message.update({"code": code})
    return message


def format_message(message):
    if isinstance(message, list):
        return message
    if not message:
        message = "The resource you requested is no longer " "available. Please modify your request and try again"
    if isinstance(message, str):
        message = {"message": message}
    return message


def get_binary_url(model_name, record_id, field_name):
    base_url = request.env["ir.config_parameter"].sudo(
    ).get_param("web.base.url")
    return f"{base_url}/portal/image/{model_name}/{record_id}/{field_name}"


def format_search_read_result(search_result, fields, duration_fields, model_name=None):
    """Format the result for search_read odoo orm method:
        - For m2o field : display only the name of record without id
        - For field of type date: cast result to str
        - Format field of type float_time using odoo tools format_duration
        - decode bytes fields using utf-8
        - Else return value
    :param search_result: List of dict result of search_read
    :param fields: fields to be formatted
    :param duration_fields: List of float_time fields , we need to format the float_time fields
    :return: List of dict if len of result > 1 else dict
    """
    result = []

    for item in search_result:
        processed_item = {}

        for key in fields:
            value = item.get(key)
            if item.get("id") and model_name and isinstance(item[key], bytes):
                processed_item[key] = get_binary_url(
                    model_name, item.get("id"), key)
            elif isinstance(value, tuple):
                processed_item[key] = value[1]
            elif isinstance(value, date):
                processed_item[key] = str(value)
            elif key in duration_fields:
                processed_item[key] = format_duration(value)
            elif isinstance(value, bytes):
                processed_item[key] = value.decode("utf-8") or False
            else:
                processed_item[key] = value

        result.append(processed_item)
    return result


def create_attachments(values):
    """Create attachments from given values.
    values: List of dict
            [ {"filename": , "data": },
              {"filename": , "data": },
              ...]
    :return list of ids for created attachments
    """
    attachment_ids = []
    for item in values:
        attachment_vals = {
            "name": item["filename"],
            "res_name": item["filename"],
            "type": "binary",
            "datas": item["data"],
        }
        attachment = request.env["ir.attachment"].sudo().create(
            attachment_vals)
        attachment_ids.append(attachment.id)
    return attachment_ids


def get_employee_image(employee_id):
    """Return the image profile for given employee"""
    result = request.env["hr.employee"].search_read(
        [("id", "=", employee_id)], ["image_128"])
    return result[0]["image_128"] and result[0]["image_128"].decode("utf-8") or False


def get_employee_name(employee_id):
    """Return the display name for given employee"""
    result = request.env["hr.employee"].search_read(
        [("id", "=", employee_id)], ["display_name"])
    return result[0]["display_name"] or False


def convert_utc_to_timezone(date_in_utc, target_tz_name="Asia/Riyadh"):
    # Localize the datetime object to UTC
    date_in_utc = pytz.utc.localize(date_in_utc)

    # Convert the datetime object to the target timezone
    target_timezone = pytz.timezone(target_tz_name)
    date_in_target_tz = date_in_utc.astimezone(target_timezone)

    # Format the date to the desired format
    formatted_date = date_in_target_tz.strftime("%Y-%m-%d %H:%M:%S")

    return formatted_date
