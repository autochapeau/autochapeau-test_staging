import logging
import re
from datetime import datetime, timezone

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GoogleReviewSource(models.Model):
    _name = "portal.google.review.source"
    _description = "Google Business Profile Reviews"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(string="Automatic Import")
    location_name = fields.Char(required=True, help="accounts/ACCOUNT_ID/locations/LOCATION_ID")
    maps_url = fields.Char(string="Google Maps Link")
    client_id = fields.Char(groups="base.group_system", copy=False)
    client_secret = fields.Char(groups="base.group_system", copy=False)
    refresh_token = fields.Char(groups="base.group_system", copy=False)
    display_limit = fields.Integer(default=10, help="Maximum latest five-star reviews on the website, across connected sources.")
    last_sync = fields.Datetime(readonly=True)
    last_error = fields.Char(readonly=True)

    @api.constrains("location_name", "maps_url", "display_limit")
    def _validate_source(self):
        for source in self:
            if not re.fullmatch(r"accounts/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+", source.location_name or ""):
                raise ValidationError(_("Use the Google location name accounts/ACCOUNT_ID/locations/LOCATION_ID."))
            if not 1 <= source.display_limit <= 100:
                raise ValidationError(_("The display limit must be between 1 and 100."))
            if source.maps_url and not source.maps_url.startswith("https://"):
                raise ValidationError(_("Use an HTTPS Google Maps link."))

    def _fetch_reviews(self):
        self.ensure_one()
        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise UserError(_("Configure authorized Google OAuth credentials before importing reviews."))
        response = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": self.refresh_token, "grant_type": "refresh_token",
        }, timeout=20)
        response.raise_for_status()
        access_token = response.json().get("access_token")
        if not access_token:
            raise UserError(_("Google did not return an access token. Reconnect the authorized account."))
        reviews = []
        page_token = None
        seen_tokens = set()
        while True:
            params = {"pageSize": 50, "orderBy": "updateTime desc"}
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(
                "https://mybusiness.googleapis.com/v4/" + self.location_name + "/reviews",
                headers={"Authorization": "Bearer " + access_token}, params=params, timeout=20,
            )
            response.raise_for_status()
            body = response.json()
            reviews.extend(body.get("reviews", []))
            page_token = body.get("nextPageToken")
            if not page_token:
                return reviews
            if page_token in seen_tokens:
                raise UserError(_("Google returned a repeated page token. Please retry the import."))
            seen_tokens.add(page_token)

    def _apply_reviews(self, reviews):
        self.ensure_one()
        testimony = self.env["portal.testimony"].sudo().with_context(active_test=False)
        retained = []
        for review in reviews:
            review_id = review.get("reviewId")
            if not review_id or review.get("starRating") != "FIVE":
                continue
            raw_time = review.get("createTime") or review.get("updateTime")
            if not raw_time:
                continue
            timestamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
            author = review.get("reviewer") or {}
            values = {
                "name": author.get("displayName") or _("Google reviewer"),
                "summary": review.get("comment") or "", "date": timestamp.date(),
                "google_source_id": self.id, "google_review_id": review_id,
                "review_time": timestamp, "rating": 5, "active": True,
                "profile_image_url": author.get("profilePhotoUrl") or False,
                "review_url": self.maps_url or False,
            }
            existing = testimony.search([("google_source_id", "=", self.id), ("google_review_id", "=", review_id)], limit=1)
            if existing:
                existing.write(values)
            else:
                existing = testimony.create(values)
            retained.append(existing.id)
        # A successful complete scan also retires removed or downgraded reviews.
        testimony.search([("google_source_id", "=", self.id), ("id", "not in", retained)]).write({"active": False})
        self.write({"last_sync": fields.Datetime.now(), "last_error": False})
        return len(retained)

    def action_sync(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only administrators can synchronize Google reviews."))
        try:
            self._apply_reviews(self._fetch_reviews())
        except (requests.RequestException, ValueError, KeyError):
            raise UserError(_("Google reviews could not be imported. Check account access and API configuration.")) from None
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "message": _("Google reviews synchronized."), "type": "success", "sticky": False,
        }}

    @api.model
    def _cron_sync(self):
        for source in self.sudo().search([("enabled", "=", True)]):
            try:
                with self.env.cr.savepoint():
                    source._apply_reviews(source._fetch_reviews())
            except Exception as error:
                # Never persist provider response bodies, OAuth tokens or secrets.
                source.last_error = _("Synchronization failed. Check Google account configuration.")
                _logger.warning("Google review source %s failed (%s)", source.id, type(error).__name__)


class GoogleTestimony(models.Model):
    _inherit = "portal.testimony"

    google_source_id = fields.Many2one("portal.google.review.source", ondelete="cascade", index=True, copy=False)
    google_review_id = fields.Char(index=True, copy=False)
    review_time = fields.Datetime(index=True)
    rating = fields.Integer(default=5)
    profile_image_url = fields.Char()
    review_url = fields.Char()

    _sql_constraints = [("google_review_unique", "unique(google_source_id, google_review_id)",
                         "This Google review has already been imported.")]
