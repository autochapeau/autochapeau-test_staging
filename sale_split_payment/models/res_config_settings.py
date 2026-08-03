from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    card_terminal_url = fields.Char(
        string="Card Terminal Sale URL",
        config_parameter="sale_split_payment.card_terminal_url",
    )
    card_terminal_status_url = fields.Char(
        string="Card Terminal Status URL",
        config_parameter="sale_split_payment.card_terminal_status_url",
        help="Optional URL template. Use {reference} for the terminal transaction reference.",
    )
    card_terminal_token = fields.Char(
        string="Card Terminal API Token",
        config_parameter="sale_split_payment.card_terminal_token",
    )
    card_terminal_timeout = fields.Integer(
        string="Card Terminal Timeout",
        config_parameter="sale_split_payment.card_terminal_timeout",
        default=60,
    )
    tabby_checkout_api_url = fields.Char(
        string="Tabby Checkout API URL",
        config_parameter="tabby.checkout_api_url",
    )
    tabby_payment_api_url = fields.Char(
        string="Tabby Payment Status API URL",
        config_parameter="tabby.payment_api_url",
        help="Base URL used to verify a payment, without the payment ID.",
    )
    tabby_secret_key = fields.Char(
        string="Tabby Secret Key",
        config_parameter="tabby.secret_key",
    )
    tabby_merchant_code = fields.Char(
        string="Tabby Merchant Code",
        config_parameter="tabby.merchant_code",
    )
    tabby_environment = fields.Selection(
        [("test", "Test"), ("production", "Production")],
        string="Tabby Environment",
        config_parameter="tabby.environment",
        default="test",
    )
