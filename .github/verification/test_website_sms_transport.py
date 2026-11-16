"""Standalone transport tests. Every provider call is mocked; no SMS is sent."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import requests

odoo_stub = types.ModuleType("odoo")
odoo_stub._ = lambda value: value
exceptions_stub = types.ModuleType("odoo.exceptions")
exceptions_stub.UserError = type("UserError", (Exception,), {})
http_stub = types.ModuleType("odoo.http")
http_stub.request = Mock()
sys.modules.update({"odoo": odoo_stub, "odoo.exceptions": exceptions_stub, "odoo.http": http_stub})
source = Path(__file__).resolve().parents[2] / "portal_api/controllers/sms.py"
spec = importlib.util.spec_from_file_location("website_sms_under_test", source)
sms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sms)


class SmsTransportTests(unittest.TestCase):
    def setUp(self):
        self.parameters = Mock()
        self.parameters.sudo.return_value = self.parameters
        self.values = {"infinito_client_id": "fake-client", "infinito_client_password": "fake-secret"}
        self.parameters.get_param.side_effect = lambda key, default="": self.values.get(key, default)
        sms.request.env.__getitem__ = Mock(return_value=self.parameters)

    def response(self, text="statustext=Success&messageid=example"):
        response = Mock(status_code=200, text=text)
        response.json.side_effect = ValueError("not JSON")
        return response

    def test_normalizes_network_numbers_without_carrier_specific_restrictions(self):
        for value in ("0555000011", "555000011", "966555000011", "00966555000011", "+966555000011", "+9660555000011"):
            self.assertEqual(sms.normalize_phone(value), "+966555000011")
        self.assertEqual(sms.normalize_phone("+201000000001"), "+201000000001")

    def test_rejects_invalid_phone(self):
        for value in ("", "email@example.com", "12"):
            with self.assertRaises(exceptions_stub.UserError):
                sms.normalize_phone(value)

    def test_form_success_returns_true(self):
        with patch.object(sms.requests, "get", return_value=self.response()) as send:
            self.assertIs(sms.send_sms("0555000011", "Test OTP"), True)
            self.assertEqual(send.call_args.kwargs["params"]["to"], "966555000011")
            self.assertEqual(send.call_args.kwargs["timeout"], 15)
            self.assertIs(send.call_args.kwargs["allow_redirects"], False)

    def test_json_success(self):
        response = Mock(status_code=200)
        response.json.return_value = {"statustext": "Success"}
        with patch.object(sms.requests, "get", return_value=response):
            self.assertTrue(sms.send_sms("0555000011", "Test OTP"))

    def test_json_acknowledgement_success_and_recipient_failure(self):
        response = Mock(status_code=200)
        payload = {"status": "Success", "statuscode": 200, "statustext": "OK",
                   "messageack": {"guids": [{"guid": "qa-message"}]}}
        response.json.return_value = payload
        self.assertTrue(sms._infinito_response_accepted(response))
        payload["messageack"]["guids"][0]["errors"] = [{"errorcode": 28682}]
        self.assertFalse(sms._infinito_response_accepted(response))

    def test_conflicting_failure_code_never_reports_success(self):
        self.assertFalse(sms._infinito_response_accepted(
            self.response("statuscode=57091&statustext=Success")))

    def test_forbidden_is_distinguished_from_wrong_credentials_without_body_logging(self):
        self.assertEqual(sms._infinito_failure_category(Mock(status_code=409, text="Forbidden")), "api_access_denied")
        self.assertEqual(sms._infinito_failure_category(Mock(status_code=401, text="private-response")), "authentication_rejected")
        response = Mock(status_code=200, text="")
        response.json.return_value = {"statuscode": 57090, "statustext": "private-response"}
        self.assertEqual(sms._infinito_failure_category(response), "credit_expired")

    def test_provider_rejection_is_not_reported_as_success(self):
        with patch.object(sms.requests, "get", return_value=self.response("statustext=Rejected")):
            with self.assertRaises(exceptions_stub.UserError):
                sms.send_sms("0555000011", "Test OTP")

    def test_network_error_does_not_expose_credentials(self):
        with patch.object(sms.requests, "get", side_effect=requests.Timeout("secret-in-request-url")):
            with self.assertRaises(exceptions_stub.UserError) as error:
                sms.send_sms("0555000011", "Test OTP")
            self.assertNotIn("secret-in-request-url", str(error.exception))

    def test_missing_configuration_never_calls_provider(self):
        self.values.clear()
        with patch.object(sms.requests, "get") as send:
            with self.assertRaises(exceptions_stub.UserError):
                sms.send_sms("0555000011", "Test OTP")
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
