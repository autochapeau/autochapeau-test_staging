import json

from werkzeug.exceptions import NotFound

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import html2plaintext, plaintext2html

from odoo.addons.im_livechat.controllers.chatbot import LivechatChatbotScriptController
from odoo.addons.im_livechat.controllers.cors.thread import LivechatThreadController
from odoo.addons.im_livechat.controllers.main import LivechatController
from odoo.addons.im_livechat.tools.misc import force_guest_env

ANSWER_STEP_TYPES = {
    "free_input_multi",
    "free_input_single",
    "question_selection",
    "question_email",
    "question_phone",
}
JSON_RPC_KEYS = {"jsonrpc", "method", "id"}


class LivechatWebApi(http.Controller):
    """Public API for an external website chatbot.

    The website never talks to the internal Live Chat routes. It calls:

    - POST /v1/livechat/init
    - POST /v1/livechat/send
    - POST /v1/livechat/messages
    - POST /v1/livechat/leave
    - POST /v1/livechat/restart
    """

    @http.route("/v1/livechat/init", type="json", auth="public", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    def livechat_init(self, **kwargs):
        data = self._data(kwargs)
        if data is None:
            return self._error(422, "Payload validation error")
        try:
            channel, error = self._channel_from_data(data)
            if error:
                return error
            self._apply_request_context(data)
            return self._init_payload(channel)
        except (UserError, ValidationError) as error:
            return self._error(422, error.args[0] if error.args else str(error))
        except Exception as error:
            return self._error(500, str(error))

    @http.route("/v1/livechat/send", type="json", auth="public", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    def livechat_send(self, **kwargs):
        """Post the visitor answer and return the next chatbot step.

        The first call omits uuid and guest_token. Every later call sends both
        back. Messages in the response are only the ones created by this call.
        """
        data = self._data(kwargs)
        if data is None:
            return self._error(422, "Payload validation error")
        try:
            self._apply_request_context(data)
            uuid = data.get("uuid")
            guest_token = data.get("guest_token")
            if uuid or guest_token:
                return self._send_existing(data)
            return self._send_new(data)
        except NotFound:
            return self._error(404, "Session not found")
        except (UserError, ValidationError) as error:
            return self._error(422, error.args[0] if error.args else str(error))
        except Exception as error:
            return self._error(500, str(error))

    @http.route(
        "/v1/livechat/messages", type="json", auth="public", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    def livechat_messages(self, **kwargs):
        data = self._data(kwargs)
        if data is None:
            return self._error(422, "Payload validation error")
        try:
            channel = self._authorized_channel(data)
            if not channel:
                return self._error(404, "Session not found")
            after_id = self._int_or_none(data.get("after_id"))
            limit = self._int_or_none(data.get("limit")) or 50
            return {
                "code": 200,
                "session_id": channel.id,
                "uuid": channel.uuid,
                "live": bool(channel.livechat_active),
                "messages": self._transcript(channel, after_id=after_id, limit=limit),
                "operator": self._operator_payload(channel),
            }
        except Exception as error:
            return self._error(500, str(error))

    @http.route("/v1/livechat/leave", type="json", auth="public", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    def livechat_leave(self, **kwargs):
        data = self._data(kwargs)
        if data is None:
            return self._error(422, "Payload validation error")
        try:
            channel = self._authorized_channel(data)
            if not channel:
                return self._error(404, "Session not found")
            if channel.livechat_active:
                LivechatController().visitor_leave_session(channel.uuid)
            return {"code": 200, "message": "Session closed", "uuid": channel.uuid}
        except Exception as error:
            return self._error(500, str(error))

    @http.route(
        "/v1/livechat/restart", type="json", auth="public", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    def livechat_restart(self, **kwargs):
        data = self._data(kwargs)
        if data is None:
            return self._error(422, "Payload validation error")
        try:
            self._apply_request_context(data)
            channel = self._authorized_channel(data)
            if not channel:
                return self._error(404, "Session not found")
            if not channel.livechat_active:
                return self._error(422, "Session is closed. Start a new one without uuid.")
            script = channel.chatbot_current_step_id.chatbot_script_id
            if not script:
                return self._error(422, "This session has no chatbot to restart")
            before_id = self._last_message_id(channel)
            LivechatChatbotScriptController().chatbot_restart(channel.uuid, script.id)
            self._apply_request_context(data)
            channel = self._reload(channel)
            self._advance(channel, data, script_id=script.id, force=True)
            channel = self._reload(channel)
            return self._session_payload(channel, before_id=before_id, is_new_session=False)
        except (UserError, ValidationError) as error:
            return self._error(422, error.args[0] if error.args else str(error))
        except Exception as error:
            return self._error(500, str(error))

    def _send_new(self, data):
        channel_config, error = self._channel_from_data(data)
        if error:
            return error
        self._apply_request_context(data)
        init_data = LivechatController().livechat_init(channel_config.id)
        if not init_data.get("available_for_me"):
            return self._error(422, "No operator is online and the chatbot is not available on this page.")
        script_id = (init_data.get("rule") or {}).get("chatbot", {}).get("scriptId")
        anonymous_name = self._anonymous_name(data)
        body, answer, error = self._prepare_visitor_input(data, script_id=script_id, channel=None)
        if error:
            return error
        session = LivechatController().get_session(
            channel_id=channel_config.id,
            anonymous_name=anonymous_name,
            chatbot_script_id=script_id or None,
            persisted=True,
        )
        if not session:
            return self._error(422, "Could not start a conversation. Check that an operator or a chatbot is available.")
        discuss = self._reload_by_uuid(session.get("uuid"))
        if not discuss:
            return self._error(422, "Could not start a conversation. Check that an operator or a chatbot is available.")
        self._rename_guest(session.get("guest_token"), anonymous_name)
        if script_id:
            self._apply_request_context(data)
            LivechatChatbotScriptController().chatbot_post_welcome_steps(discuss.uuid, script_id)
            discuss = self._reload(discuss)
        data["guest_token"] = session.get("guest_token") or self._guest_token(discuss)
        input_error = self._accept_visitor_input(discuss, data, body, answer)
        if input_error:
            payload = self._session_payload(discuss, before_id=0, is_new_session=True)
            payload.update(input_error)
            return payload
        discuss = self._reload(discuss)
        if script_id and self._should_advance(discuss):
            self._apply_request_context(data)
            self._advance(discuss, data, script_id=script_id)
        return self._session_payload(self._reload(discuss), before_id=0, is_new_session=True)

    def _send_existing(self, data):
        if not data.get("uuid") or not data.get("guest_token"):
            return self._error(422, "uuid and guest_token are required to continue a session")
        channel = self._authorized_channel(data)
        if not channel:
            return self._error(404, "Session not found")
        if not channel.livechat_active:
            return self._error(422, "Session is closed. Start a new one without uuid.")
        before_id = self._last_message_id(channel)
        body, answer, error = self._prepare_visitor_input(
            data, script_id=channel.chatbot_current_step_id.chatbot_script_id.id, channel=channel
        )
        if error:
            return error
        input_error = self._accept_visitor_input(channel, data, body, answer)
        if input_error:
            payload = self._session_payload(self._reload(channel), before_id=before_id, is_new_session=False)
            payload.update(input_error)
            return payload
        channel = self._reload(channel)
        if self._should_advance(channel):
            self._apply_request_context(data)
            self._advance(channel, data)
        return self._session_payload(self._reload(channel), before_id=before_id, is_new_session=False)

    def _accept_visitor_input(self, channel, data, body, answer):
        step = channel.chatbot_current_step_id
        if answer and (not step or answer.script_step_id != step):
            return self._error(422, "selected_answer_id does not belong to the current question")
        if step and step.answer_ids and not answer:
            return self._error(422, "selected_answer_id is required for this question")
        question_message = self._bot_question_message(channel) if answer else False
        self._post_visitor_message(channel, data.get("guest_token"), body)
        channel = self._reload(channel)
        if answer and question_message:
            self._apply_request_context(data)
            LivechatChatbotScriptController().chatbot_save_answer(channel.uuid, question_message.id, answer.id)
        if step and step.step_type == "question_email":
            self._apply_request_context(data)
            validation = LivechatChatbotScriptController().chatbot_validate_email(channel.uuid) or {}
            if not validation.get("success"):
                return self._error(
                    422, validation.get("error_message") or "This email address is not valid"
                )
        return False

    def _advance(self, channel, data, script_id=None, force=False):
        """Walk the script until the visitor has to answer, or the script ends."""
        if not force and not self._should_advance(channel):
            return
        controller = LivechatChatbotScriptController()
        for _index in range(12):
            channel = self._reload(channel)
            script = channel.chatbot_current_step_id.chatbot_script_id
            current_script_id = script.id or script_id
            if not current_script_id:
                return
            self._apply_request_context(data)
            result = controller.chatbot_trigger_step(channel.uuid, current_script_id)
            if not result:
                return
            step_data = result.get("chatbot_step") or {}
            if step_data.get("operatorFound"):
                return
            step_type = step_data.get("type")
            if step_data.get("answers") or step_type in ANSWER_STEP_TYPES:
                return
            if step_data.get("isLast"):
                return

    def _prepare_visitor_input(self, data, script_id, channel):
        raw_answer_id = data.get("selected_answer_id")
        answer = self._answer_from_data(raw_answer_id)
        if raw_answer_id not in (None, False, "") and not answer:
            return False, answer, self._error(422, "selected_answer_id was not found")
        body = (data.get("body") or "").strip()
        if answer and not body:
            body = answer.name or ""
        if not body:
            return False, answer, self._error(422, "body is required")
        if answer and channel and answer.script_step_id != channel.chatbot_current_step_id:
            return False, answer, self._error(422, "selected_answer_id does not belong to the current question")
        if not channel and script_id:
            welcome = self._welcome_question(script_id)
            if welcome and welcome.answer_ids and not answer:
                return False, answer, self._error(422, "selected_answer_id is required for this question")
            if answer and (not welcome or answer.script_step_id != welcome):
                return False, answer, self._error(422, "selected_answer_id does not belong to the current question")
        return body, answer, False

    def _init_payload(self, channel):
        init_data = LivechatController().livechat_init(channel.id)
        info = channel._get_channel_infos()
        rule = init_data.get("rule") or {}
        chatbot = rule.get("chatbot") or {}
        welcome_steps = [self._format_frontend_step(step) for step in chatbot.get("welcomeSteps") or []]
        return {
            "code": 200,
            "available": bool(init_data.get("available_for_me")),
            "channel_id": channel.id,
            "channel_name": info.get("channel_name"),
            "button_text": info.get("button_text"),
            "welcome_message": info.get("default_message"),
            "input_placeholder": info.get("input_placeholder"),
            "action": rule.get("action") or "display_button",
            "auto_popup_timer": rule.get("auto_popup_timer") or 0,
            "colors": {
                "header_background": info.get("header_background_color"),
                "title": info.get("title_color"),
                "button_background": info.get("button_background_color"),
                "button_text": info.get("button_text_color"),
            },
            "chatbot": {
                "id": chatbot.get("scriptId"),
                "name": chatbot.get("name"),
                "welcome_steps": welcome_steps,
            }
            if chatbot
            else False,
        }

    def _session_payload(self, channel, before_id, is_new_session):
        channel = self._reload(channel)
        step = channel.chatbot_current_step_id
        operator = self._operator_payload(channel)
        operator_found = bool(operator and operator.get("is_human"))
        expects_answer = self._expects_answer(channel) and not operator_found
        has_answers = bool(step and step.answer_ids)
        messages = self._transcript(channel, after_id=before_id or None, limit=100)
        return {
            "code": 200,
            "is_new_session": is_new_session,
            "channel_id": channel.livechat_channel_id.id,
            "session_id": channel.id,
            "uuid": channel.uuid,
            "guest_token": self._guest_token(channel),
            "live": bool(channel.livechat_active),
            "operator_found": operator_found,
            "done": not operator_found and not expects_answer,
            "input_enabled": bool(operator_found or (expects_answer and not has_answers)),
            "operator": operator,
            "step": self._format_step(step, channel, operator_found) if expects_answer else False,
            "messages": messages,
        }

    def _post_visitor_message(self, channel, guest_token, body):
        token = guest_token or self._guest_token(channel)
        if not token:
            raise UserError("guest_token is missing")
        LivechatThreadController().livechat_message_post(
            guest_token=token,
            thread_model="discuss.channel",
            thread_id=channel.id,
            post_data={
                "body": str(plaintext2html(body)),
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment",
            },
        )

    def _channel_from_data(self, data):
        channel_id = self._int_or_none(data.get("channel_id"))
        channel_model = request.env["im_livechat.channel"].sudo()
        if channel_id:
            channel = channel_model.browse(channel_id).exists()
            if not channel:
                return False, self._error(404, "channel_id was not found")
            return channel, False
        channels = channel_model.search([])
        if len(channels) == 1:
            return channels, False
        if not channels:
            return False, self._error(422, "Create a Live Chat channel first")
        return False, {
            "code": 422,
            "message": "channel_id is required",
            "channels": [{"id": channel.id, "name": channel.name} for channel in channels],
        }

    def _authorized_channel(self, data):
        guest_token = data.get("guest_token")
        uuid = data.get("uuid")
        session_id = self._int_or_none(data.get("session_id"))
        if not guest_token or not (uuid or session_id):
            return request.env["discuss.channel"]
        force_guest_env(guest_token, raise_if_not_found=False)
        guest = request.env["mail.guest"]._get_guest_from_context()
        if not guest:
            return request.env["discuss.channel"]
        domain = [
            ("channel_type", "=", "livechat"),
            ("channel_member_ids.guest_id", "=", guest.id),
        ]
        if uuid:
            domain.append(("uuid", "=", uuid))
        if session_id:
            domain.append(("id", "=", session_id))
        return request.env["discuss.channel"].sudo().search(domain, limit=1)

    def _welcome_question(self, script_id):
        script = request.env["chatbot.script"].sudo().browse(int(script_id)).exists()
        if not script:
            return request.env["chatbot.script.step"]
        steps = script._get_welcome_steps()
        return steps[-1] if steps else request.env["chatbot.script.step"]

    def _answer_from_data(self, answer_id):
        answer_id = self._int_or_none(answer_id)
        if not answer_id:
            return request.env["chatbot.script.answer"]
        return request.env["chatbot.script.answer"].sudo().browse(answer_id).exists()

    def _bot_question_message(self, channel):
        step = channel.chatbot_current_step_id
        if not step:
            return request.env["mail.message"]
        bot_partner = step.chatbot_script_id.operator_partner_id
        messages = channel.chatbot_message_ids.filtered(
            lambda item: item.script_step_id == step and item.mail_message_id.author_id == bot_partner
        ).sorted("id")
        return messages[-1].mail_message_id if messages else request.env["mail.message"]

    def _should_advance(self, channel):
        """True when the message just posted is an answer the script still has to consume."""
        step = channel.chatbot_current_step_id
        if not step or self._human_partner(channel):
            return False
        return bool(step.answer_ids) or step.step_type in ANSWER_STEP_TYPES

    def _expects_answer(self, channel):
        """True when the website must wait for the visitor before calling send again."""
        step = channel.chatbot_current_step_id
        if not step or step.step_type == "forward_operator":
            return False
        question = self._bot_question_message(channel)
        if step.step_type == "question_email":
            if question:
                chatbot_message = channel.chatbot_message_ids.filtered(
                    lambda item: item.mail_message_id == question
                )[:1]
                if chatbot_message.user_raw_answer:
                    return False
            return True
        if step.answer_ids:
            if question:
                chatbot_message = channel.chatbot_message_ids.filtered(
                    lambda item: item.mail_message_id == question
                )[:1]
                if chatbot_message.user_script_answer_id:
                    return False
            return True
        if step.step_type in ANSWER_STEP_TYPES:
            if question and channel.message_ids.filtered(
                lambda message: message.id > question.id and message.author_guest_id
            ):
                return False
            return True
        return False

    def _human_partner(self, channel):
        bot = channel.chatbot_current_step_id.chatbot_script_id.operator_partner_id
        for member in channel.channel_member_ids:
            if member.guest_id or not member.partner_id:
                continue
            if bot and member.partner_id == bot:
                continue
            return member.partner_id
        if not bot and channel.livechat_operator_id:
            return channel.livechat_operator_id
        return request.env["res.partner"]

    def _operator_payload(self, channel):
        human = self._human_partner(channel)
        partner = human or channel.livechat_operator_id
        if not partner:
            return False
        name = getattr(partner, "user_livechat_username", False) or partner.name
        return {"id": partner.id, "name": name, "is_human": bool(human)}

    def _format_step(self, step, channel, operator_found):
        if not step:
            return False
        return {
            "id": step.id,
            "type": step.step_type,
            "message": str(plaintext2html(step.message)) if step.message else False,
            "answers": [
                {"id": answer.id, "label": answer.name, "redirect_link": answer.redirect_link or False}
                for answer in step.answer_ids
            ],
            "is_last": bool(step._is_last_step(channel)),
            "operator_found": operator_found,
        }

    def _format_frontend_step(self, step):
        return {
            "id": step.get("id"),
            "type": step.get("type"),
            "message": str(step.get("message") or "") or False,
            "answers": [
                {
                    "id": answer.get("id"),
                    "label": answer.get("label"),
                    "redirect_link": answer.get("redirectLink") or False,
                }
                for answer in step.get("answers") or []
            ],
            "is_last": bool(step.get("isLast")),
        }

    def _transcript(self, channel, after_id=None, limit=50):
        bot = channel.chatbot_current_step_id.chatbot_script_id.operator_partner_id
        messages = channel.message_ids.filtered(lambda message: message.message_type != "user_notification").sorted(
            key=lambda message: message.id
        )
        if after_id:
            messages = messages.filtered(lambda message: message.id > after_id)
            messages = messages[:limit]
        else:
            messages = messages[-limit:]
        return [self._format_message(message, bot) for message in messages]

    def _format_message(self, message, bot):
        author = message.author_id
        guest = message.author_guest_id
        is_bot = bool(bot and author and author == bot)
        return {
            "id": message.id,
            "body": str(message.body or ""),
            "text": html2plaintext(message.body or "").strip(),
            "date": fields.Datetime.to_string(message.date),
            "author_name": author.name if author else (guest.name if guest else False),
            "is_visitor": bool(guest),
            "is_bot": is_bot,
            "is_operator": bool(author and not is_bot and message.message_type == "comment"),
        }

    def _rename_guest(self, guest_token, anonymous_name):
        if not guest_token or not anonymous_name:
            return
        guest = request.env["mail.guest"].sudo()._get_guest_from_token(guest_token)
        if guest and guest.name != anonymous_name:
            guest.sudo().write({"name": anonymous_name})

    def _guest_token(self, channel):
        guest = channel.channel_member_ids.filtered("guest_id").guest_id[:1]
        if not guest:
            return False
        return guest.sudo()._format_auth_cookie()

    def _anonymous_name(self, data):
        return (data.get("anonymous_name") or data.get("name") or "Visitor").strip() or "Visitor"

    def _apply_request_context(self, data):
        lang = data.get("lang") or request.httprequest.args.get("lang") or "en_US"
        if lang in ("ar", "ar_SA", "ar_001"):
            lang = "ar_001"
        elif lang in ("en", "en_US"):
            lang = "en_US"
        page_url = data.get("page_url")
        if page_url:
            request.httprequest.environ["HTTP_REFERER"] = page_url
        cookies = dict(request.httprequest.cookies or {})
        cookies["frontend_lang"] = lang
        request.httprequest.cookies = cookies
        request.update_context(lang=lang)

    def _reload(self, channel):
        return request.env["discuss.channel"].sudo().browse(channel.id)

    def _reload_by_uuid(self, uuid):
        return request.env["discuss.channel"].sudo().search(
            [("uuid", "=", uuid), ("channel_type", "=", "livechat")], limit=1
        )

    def _last_message_id(self, channel):
        messages = channel.message_ids
        return max(messages.ids) if messages else 0

    def _data(self, kwargs):
        raw = request.httprequest.data
        payload = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except ValueError:
                return None
            if not isinstance(parsed, dict):
                return None
            if isinstance(parsed.get("params"), dict):
                payload = parsed["params"]
            else:
                payload = {key: value for key, value in parsed.items() if key not in JSON_RPC_KEYS}
        return {**kwargs, **payload}

    def _int_or_none(self, value):
        if value in (None, False, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _error(self, code, message):
        return {"code": code, "message": message}
