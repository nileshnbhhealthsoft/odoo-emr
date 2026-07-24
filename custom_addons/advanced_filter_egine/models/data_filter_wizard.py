# -*- coding: utf-8 -*-

from ast import literal_eval

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression


class DataFilterWizard(models.TransientModel):
    _name = "data.filter.wizard"
    _description = "Dynamic Data Filter Wizard"

    model_id = fields.Many2one("ir.model", string="Target Model", required=True, ondelete="cascade")
    model_name = fields.Char(string="Target Model Technical Name", related="model_id.model", readonly=True)
    domain = fields.Char(
        string="Domain",
        default="[]",
        help="Native Odoo domain applied to the selected target model.",
    )
    group_by_field_ids = fields.Many2many(
        "ir.model.fields",
        string="Group By",
        domain="[('model_id', '=', model_id), ('ttype', 'not in', ('binary', 'one2many', 'many2many'))]",
    )
    result_count = fields.Integer(string="Record Count", compute="_compute_result_count")

    @api.depends("model_name", "domain")
    def _compute_result_count(self):
        for wizard in self:
            try:
                wizard.result_count = self.env[wizard.model_name].search_count(wizard._get_domain())
            except (KeyError, UserError, ValueError, TypeError, SyntaxError):
                wizard.result_count = 0

    @api.onchange("model_id")
    def _onchange_model_id(self):
        self.domain = "[]"
        self.group_by_field_ids = [(5, 0, 0)]

    def _get_domain(self):
        self.ensure_one()
        if not self.model_name or self.model_name not in self.env:
            raise UserError(_("Select a valid target model."))
        raw_domain = (self.domain or "[]").strip() or "[]"
        try:
            domain = literal_eval(raw_domain)
        except (ValueError, SyntaxError) as error:
            raise UserError(_("Domain is not valid.")) from error
        if not isinstance(domain, list):
            raise UserError(_("Domain must be a list domain."))
        try:
            return expression.normalize_domain(domain)
        except (AssertionError, ValueError, TypeError) as error:
            raise UserError(_("Domain is not valid.")) from error

    def action_open_records(self):
        self.ensure_one()
        context = dict(self.env.context)
        group_by = self.group_by_field_ids.mapped("name")
        if group_by:
            context["group_by"] = group_by
        return {
            "type": "ir.actions.act_window",
            "name": _("Filtered %(model)s") % {"model": self.model_id.name},
            "res_model": self.model_name,
            "view_mode": "list,form",
            "domain": self._get_domain(),
            "context": context,
            "target": "current",
        }
