# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

MESSAGE_COLOR_SELECTION = [
    ("automatic", "Automatic"),
    ("#0D6EFD", "Blue"),
    ("#198754", "Green"),
    ("#DC3545", "Red"),
    ("#6F42C1", "Purple"),
    ("#D63384", "Pink"),
    ("#FD7E14", "Orange"),
    ("#20C997", "Teal"),
    ("#374151", "Dark Gray"),
    ("#1D4ED8", "Navy"),
    ("#047857", "Emerald"),
    ("#BE123C", "Rose"),
    ("#B45309", "Amber"),
]


class ResUsers(models.Model):
    _inherit = "res.users"

    claim_service_message_color = fields.Char(
        string="Claim/Service Message Color",
        help="Hex color used for this user's 835 claim/service comments. Leave empty to use the automatic color.",
    )
    claim_service_message_color_preset = fields.Selection(
        MESSAGE_COLOR_SELECTION,
        string="Claim/Service Message Color",
        default="automatic",
        help="Color used for this user's 835 claim/service comments.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            "claim_service_message_color",
            "claim_service_message_color_preset",
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            "claim_service_message_color",
            "claim_service_message_color_preset",
        ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "claim_service_message_color_preset" in vals:
                color = vals["claim_service_message_color_preset"]
                vals["claim_service_message_color"] = color if color != "automatic" else False
        return super().create(vals_list)

    def write(self, vals):
        if "claim_service_message_color_preset" in vals:
            color = vals["claim_service_message_color_preset"]
            vals = dict(vals, claim_service_message_color=color if color != "automatic" else False)
        return super().write(vals)

    @api.constrains("claim_service_message_color")
    def _check_claim_service_message_color(self):
        for user in self:
            color = (user.claim_service_message_color or "").strip()
            if color and not HEX_COLOR_RE.match(color):
                raise ValidationError("Claim/Service Message Color must be a hex color like #0D6EFD.")
