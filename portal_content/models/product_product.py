from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    image_ids = fields.Many2many("ir.attachment", string="Images", copy=False)
    review_ids = fields.One2many("product.product.review", "product_id")
    question_ids = fields.One2many("product.product.question", "product_id")
    reviews_count = fields.Integer(
        compute="_compute_product_reviews", store=True, readonly=True)
    reviews_rate = fields.Float(
        compute="_compute_product_reviews", store=True, readonly=True)

    @api.depends("review_ids", "review_ids.published")
    def _compute_product_reviews(self):
        for product in self:
            review_published = product.review_ids.filtered(
                lambda review: review.published)
            product.reviews_count = len(review_published)
            product.reviews_rate = sum(review_published.mapped(
                "rate")) / (product.reviews_count or 1.0)


class ProductProductReview(models.Model):
    _name = "product.product.review"
    _description = "Product Review"

    product_id = fields.Many2one("product.product")
    partner_id = fields.Many2one(
        "res.partner", string="Customer", readonly=True, required=True)
    rate = fields.Integer(readonly=True)
    message = fields.Text(readonly=True)
    published = fields.Boolean()


class ProductProductQuestion(models.Model):
    _name = "product.product.question"
    _description = "Product questions"

    product_id = fields.Many2one("product.product")
    question = fields.Char(required=True, translate=True)
    answer = fields.Char(required=True, translate=True)
