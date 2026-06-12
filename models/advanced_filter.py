# -*- coding: utf-8 -*-

from ast import literal_eval
from collections import defaultdict
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression


class AdvancedFilter(models.Model):
    _name = "advanced.filter"
    _description = "Advanced Filter Engine"
    _order = "name asc"

    name = fields.Char(string="Filter Name", required=True)
    active = fields.Boolean(default=True)
    main_model_id = fields.Many2one("ir.model", string="Target Model", required=True, ondelete="cascade")
    main_model = fields.Char(string="Target Model Technical Name", related="main_model_id.model", store=True, readonly=True)
    relation_mode = fields.Selection(
        [
            ("direct", "Direct Model"),
            ("child_to_parent", "Child -> Parent"),
            ("parent_to_child", "Parent -> Child"),
            ("child_parent_child", "Child -> Parent -> Children"),
        ],
        default="direct",
        required=True,
        help="Child -> Parent filters parent records by child rows. Parent -> Child filters child records by parent rows. "
        "Child -> Parent -> Child finds parents from matching child rows, then returns all child rows under those parents.",
    )
    related_model_id = fields.Many2one("ir.model", string="Children Model", ondelete="cascade")
    related_model = fields.Char(
        string="Children Model Technical Name",
        related="related_model_id.model",
        store=True,
        readonly=True,
    )
    relation_candidate_model_ids = fields.Many2many(
        "ir.model",
        compute="_compute_relation_candidate_model_ids",
        string="Relation Candidate Models",
    )
    relation_field_id = fields.Many2one(
        "ir.model.fields",
        string="Relation Field",
        help="For Child -> Parent, choose the Many2one field on the child model pointing to the parent. "
        "For Parent -> Child, choose the Many2one field on the main child model pointing to the parent. "
        "For Child -> Parent -> Child, choose the condition child field pointing to the parent.",
    )
    result_relation_field_id = fields.Many2one(
        "ir.model.fields",
        string="Parent Relation Field",
        help="For Child -> Parent -> Children, choose the Many2one field on the final result child model pointing to the parent.",
    )
    relation_field_model = fields.Char(compute="_compute_relation_field_domain_values")
    relation_field_relation = fields.Char(compute="_compute_relation_field_domain_values")
    result_relation_field_relation = fields.Char(compute="_compute_relation_field_domain_values")
    related_match_mode = fields.Selection(
        [
            ("all", "All"),
            ("any", "Any"),
            ("none", "Not Included"),
        ],
        string="Condition",
        default="all",
        required=True,
    )
    line_ids = fields.One2many("advanced.filter.line", "filter_id", string="Filter Lines", copy=True)
    group_by_line_ids = fields.One2many("advanced.filter.group.by", "filter_id", string="Group By", copy=True)
    duplicate_detection = fields.Boolean(string="Duplicate / Aggregation Filter")
    duplicate_group_by_line_ids = fields.One2many(
        "advanced.filter.duplicate.group.by",
        "filter_id",
        string="Duplicate Group By",
        copy=True,
    )
    duplicate_count_operator = fields.Selection(
        [(">", ">"), (">=", ">="), ("=", "="), ("!=", "!="), ("<", "<"), ("<=", "<=")],
        string="Count Operator",
        default=">",
        required=True,
    )
    duplicate_count = fields.Integer(string="Count", default=1, required=True)
    user_id = fields.Many2one("res.users", string="Owner", default=lambda self: self.env.user, required=True)
    is_shared = fields.Boolean(string="Shared Filter", default=False)
    is_default = fields.Boolean(string="Default Filter", default=False)
    ir_filter_id = fields.Many2one(
        "ir.filters",
        string="Odoo Favorite",
        readonly=True,
        copy=False,
        ondelete="set null",
        help="Native Odoo favorite synchronized from this advanced filter.",
    )
    computed_domain = fields.Char(string="Computed Domain", compute="_compute_computed_domain")
    condition_summary = fields.Text(string="Readable Conditions", compute="_compute_condition_summary")
    result_count = fields.Integer(string="Record Count", compute="_compute_result_count")

    @api.depends("main_model", "relation_mode")
    def _compute_relation_candidate_model_ids(self):
        IrModel = self.env["ir.model"]
        IrModelFields = self.env["ir.model.fields"]
        for advanced_filter in self:
            candidate_models = IrModel.browse()
            if advanced_filter.main_model and advanced_filter.relation_mode == "child_to_parent":
                relation_fields = IrModelFields.search(
                    [
                        ("ttype", "=", "many2one"),
                        ("relation", "=", advanced_filter.main_model),
                    ]
                )
                candidate_models = IrModel.search([("model", "in", relation_fields.mapped("model"))])
            elif advanced_filter.main_model and advanced_filter.relation_mode == "parent_to_child":
                relation_fields = IrModelFields.search(
                    [
                        ("ttype", "=", "many2one"),
                        ("model", "=", advanced_filter.main_model),
                        ("relation", "!=", False),
                    ]
                )
                candidate_models = IrModel.search([("model", "in", relation_fields.mapped("relation"))])
            elif advanced_filter.main_model and advanced_filter.relation_mode == "child_parent_child":
                parent_fields = IrModelFields.search(
                    [
                        ("ttype", "=", "many2one"),
                        ("model", "=", advanced_filter.main_model),
                        ("relation", "!=", False),
                    ]
                )
                relation_fields = IrModelFields.search(
                    [
                        ("ttype", "=", "many2one"),
                        ("relation", "in", parent_fields.mapped("relation")),
                    ]
                )
                candidate_models = IrModel.search([("model", "in", relation_fields.mapped("model"))])
            advanced_filter.relation_candidate_model_ids = candidate_models

    @api.depends("main_model", "related_model", "relation_mode", "result_relation_field_id")
    def _compute_relation_field_domain_values(self):
        IrModelFields = self.env["ir.model.fields"]
        for advanced_filter in self:
            advanced_filter.result_relation_field_relation = False
            if advanced_filter.relation_mode == "child_to_parent":
                advanced_filter.relation_field_model = advanced_filter.related_model
                advanced_filter.relation_field_relation = advanced_filter.main_model
            elif advanced_filter.relation_mode == "parent_to_child":
                advanced_filter.relation_field_model = advanced_filter.main_model
                advanced_filter.relation_field_relation = advanced_filter.related_model
            elif advanced_filter.relation_mode == "child_parent_child":
                parent_model = advanced_filter.result_relation_field_id.relation
                advanced_filter.relation_field_model = advanced_filter.related_model
                advanced_filter.relation_field_relation = parent_model
                advanced_filter.result_relation_field_relation = parent_model
            else:
                advanced_filter.relation_field_model = False
                advanced_filter.relation_field_relation = False

    @api.depends(
        "main_model_id",
        "related_model_id",
        "relation_mode",
        "relation_field_id",
        "result_relation_field_id",
        "related_match_mode",
        "duplicate_detection",
        "duplicate_count_operator",
        "duplicate_count",
        "line_ids.condition_domain",
        "duplicate_group_by_line_ids.field_id",
        "duplicate_group_by_line_ids.date_interval",
    )
    def _compute_computed_domain(self):
        for advanced_filter in self:
            try:
                advanced_filter.computed_domain = repr(advanced_filter._build_domain_preview())
            except (UserError, ValidationError, ValueError, TypeError):
                advanced_filter.computed_domain = "[]"

    @api.depends(
        "related_match_mode",
        "line_ids.condition_domain",
    )
    def _compute_condition_summary(self):
        for advanced_filter in self:
            lines = advanced_filter._get_valid_condition_lines()
            if not lines:
                advanced_filter.condition_summary = _("No conditions")
                continue
            separator = {
                "all": _(" AND "),
                "any": _(" OR "),
                "none": _(" NOT IN "),
            }.get(advanced_filter.related_match_mode or "all")
            prefix = _("Not included in: ") if advanced_filter.related_match_mode == "none" else ""
            advanced_filter.condition_summary = prefix + separator.join(lines.mapped("condition_display"))

    @api.depends("computed_domain")
    def _compute_result_count(self):
        for advanced_filter in self:
            try:
                advanced_filter.result_count = self.env[advanced_filter.main_model].search_count(
                    advanced_filter._build_action_domain()
                )
            except (UserError, ValidationError, ValueError, TypeError, KeyError):
                advanced_filter.result_count = 0

    @api.onchange("main_model_id", "relation_mode")
    def _onchange_main_model_id(self):
        self.line_ids = [(5, 0, 0)]
        self.group_by_line_ids = [(5, 0, 0)]
        self.duplicate_group_by_line_ids = [(5, 0, 0)]
        self.related_model_id = False
        self.relation_field_id = False
        self.result_relation_field_id = False

    @api.onchange("related_model_id")
    def _onchange_related_model_id(self):
        self.line_ids = [(5, 0, 0)]
        self.relation_field_id = False

    @api.onchange("result_relation_field_id")
    def _onchange_result_relation_field_id(self):
        self.relation_field_id = False

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("advanced_filter_skip_favorite_sync"):
            self._cleanup_odoo_favorites()
        return result

    def unlink(self):
        native_filters = self.mapped("ir_filter_id").sudo()
        result = super().unlink()
        native_filters.unlink()
        return result

    @api.onchange("main_model_id", "relation_mode", "related_model_id", "result_relation_field_id")
    def _onchange_relation_field_id(self):
        for advanced_filter in self:
            if advanced_filter.relation_mode == "direct" or not advanced_filter.related_model_id:
                continue
            if advanced_filter.relation_mode == "child_parent_child" and not advanced_filter.result_relation_field_id:
                continue
            relation_fields = self.env["ir.model.fields"].search(
                [
                    ("ttype", "=", "many2one"),
                    ("model", "=", advanced_filter.relation_field_model),
                    ("relation", "=", advanced_filter.relation_field_relation),
                ]
            )
            if len(relation_fields) == 1:
                advanced_filter.relation_field_id = relation_fields

    @api.constrains("main_model_id", "related_model_id", "relation_mode", "relation_field_id", "result_relation_field_id")
    def _check_relation_config(self):
        for advanced_filter in self:
            if advanced_filter.relation_mode == "direct":
                continue
            if not advanced_filter.related_model_id or not advanced_filter.relation_field_id:
                raise ValidationError(_("Related model and relation field are required for relational filters."))
            if advanced_filter.relation_mode == "child_parent_child" and not advanced_filter.result_relation_field_id:
                raise ValidationError(_("Result relation field is required for Child -> Parent -> Child filters."))
            if advanced_filter.relation_field_id.ttype != "many2one":
                raise ValidationError(_("Relation field must be a Many2one field."))
            if advanced_filter.result_relation_field_id and advanced_filter.result_relation_field_id.ttype != "many2one":
                raise ValidationError(_("Result relation field must be a Many2one field."))
            if (
                advanced_filter.relation_field_id.model != advanced_filter.relation_field_model
                or advanced_filter.relation_field_id.relation != advanced_filter.relation_field_relation
            ):
                raise ValidationError(_("Relation field does not match the selected relational filter setup."))
            if advanced_filter.relation_mode == "child_parent_child" and (
                advanced_filter.result_relation_field_id.model != advanced_filter.main_model
                or advanced_filter.result_relation_field_id.relation != advanced_filter.result_relation_field_relation
            ):
                raise ValidationError(_("Result relation field does not match the selected target model."))

    def _get_condition_model_name(self):
        self.ensure_one()
        if self.relation_mode == "direct":
            return self.main_model
        if self.relation_mode in ("child_to_parent", "child_parent_child") and self.relation_field_model:
            return self.relation_field_model
        return self.related_model

    def _get_condition_domain(self):
        self.ensure_one()
        lines = self._get_valid_condition_lines()
        domains = [line._get_condition_domain() for line in lines]
        if not domains:
            return []
        if self.related_match_mode == "any":
            return expression.OR(domains)
        if self.related_match_mode == "none":
            return [("id", "not in", self._get_matching_main_record_ids())]
        return expression.AND(domains)

    def _get_valid_condition_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line._has_condition_domain()).sorted(lambda line: (line.sequence, line.id))

    def _build_domain_preview(self):
        self.ensure_one()
        return self._build_action_domain()

    def _build_action_domain(self):
        self.ensure_one()
        self._check_model_available(self.main_model)

        if self.relation_mode == "direct":
            if self.duplicate_detection:
                return self._get_duplicate_domain()
            matching_ids = self._get_matching_main_record_ids()
            operator = "not in" if self.related_match_mode == "none" else "in"
            return [("id", operator, list(matching_ids))]

        self._check_model_available(self.related_model)
        if not self._is_relation_config_ready():
            return []
        self._validate_relation_field()

        main_ids = self._get_matching_main_record_ids()
        operator = "not in" if self.related_match_mode == "none" else "in"
        return [("id", operator, list(main_ids))]

    def _is_relation_config_ready(self):
        self.ensure_one()
        if self.relation_mode == "direct":
            return True
        if not self.related_model or not self.relation_field_id or not self.relation_field_id.name:
            return False
        if self.relation_mode == "child_parent_child" and (
            not self.result_relation_field_id or not self.result_relation_field_id.name
        ):
            return False
        return True

    def _validate_relation_field(self):
        self.ensure_one()
        relation_field = self.relation_field_id
        if not self._is_relation_config_ready():
            raise UserError(_("Complete the relation configuration before applying the filter."))
        if self.relation_mode == "child_to_parent":
            valid_pairs = {
                (self.related_model, self.main_model),
                (self.main_model, self.related_model),
            }
            if (relation_field.model, relation_field.relation) not in valid_pairs:
                raise UserError(
                    _("Relation field must connect %(target)s and %(related)s.")
                    % {"target": self.main_model, "related": self.related_model}
                )
            return
        elif self.relation_mode == "parent_to_child":
            expected_model = self.main_model
            expected_relation = self.related_model
        else:
            result_relation_field = self.result_relation_field_id
            if result_relation_field.model != self.main_model:
                raise UserError(_("Result relation field must belong to model %s.") % self.main_model)
            expected_model = self.related_model
            expected_relation = result_relation_field.relation

        if relation_field.model != expected_model:
            raise UserError(_("Relation field must belong to model %s.") % expected_model)
        if relation_field.relation != expected_relation:
            raise UserError(_("Relation field must point to model %s.") % expected_relation)

    def _get_matching_main_record_ids(self):
        self.ensure_one()
        lines = self._get_valid_condition_lines()
        if not lines:
            if self.related_match_mode in ("any", "none"):
                return set()
            return set(self.env[self.main_model].search([]).ids)
        if self.relation_mode == "direct":
            return self._get_direct_matching_ids(lines)
        return self._get_main_record_ids_from_related_filter(lines)

    def _get_direct_matching_ids(self, lines):
        self.ensure_one()
        model = self.env[self.main_model]
        if self.related_match_mode == "all":
            result_ids = None
            for line in lines:
                domain = line._get_condition_domain()
                if result_ids is not None:
                    domain = expression.AND([domain, [("id", "in", list(result_ids))]])
                result_ids = set(model.search(domain).ids)
            return result_ids or set()
        result_ids = set()
        for line in lines:
            result_ids |= set(model.search(line._get_condition_domain()).ids)
        return result_ids

    def _get_main_record_ids_from_related_filter(self, lines):
        self.ensure_one()
        if not self._is_relation_config_ready():
            return set()

        if self.relation_mode == "child_to_parent":
            if self.relation_field_id.model == self.main_model:
                return self._get_direct_matching_ids(lines)
            return self._get_parent_ids_from_condition_child_lines(lines, self.env[self.related_model], self.relation_field_id.name)

        if self.relation_mode == "child_parent_child":
            condition_child_model = self.env[self.related_model]
            condition_parent_field = self.relation_field_id.name
            parent_ids = self._get_parent_ids_from_condition_child_lines(lines, condition_child_model, condition_parent_field)
            result_child_records = self.env[self.main_model].search([(self.result_relation_field_id.name, "in", list(parent_ids))])
            return set(result_child_records.ids)

        parent_model = self.env[self.related_model]
        child_model = self.env[self.main_model]
        parent_ids = self._get_parent_model_ids_from_lines(lines, parent_model)
        child_parent_field = self.relation_field_id.name
        child_records = child_model.search([(child_parent_field, "in", list(parent_ids))])
        return set(child_records.ids)

    def _get_parent_ids_from_condition_child_lines(self, lines, child_model, parent_field):
        self.ensure_one()
        if self.related_match_mode == "all":
            parent_ids = None
            for line in lines:
                domain = line._get_condition_domain()
                if parent_ids is not None:
                    domain = expression.AND([domain, [(parent_field, "in", list(parent_ids))]])
                child_records = child_model.search(domain + [(parent_field, "!=", False)])
                parent_ids = set(child_records.mapped(parent_field).ids)
            return parent_ids or set()
        parent_ids = set()
        for line in lines:
            child_records = child_model.search(line._get_condition_domain() + [(parent_field, "!=", False)])
            parent_ids |= set(child_records.mapped(parent_field).ids)
        return parent_ids

    def _get_parent_model_ids_from_lines(self, lines, parent_model):
        self.ensure_one()
        if self.related_match_mode == "all":
            parent_ids = None
            for line in lines:
                domain = line._get_condition_domain()
                if parent_ids is not None:
                    domain = expression.AND([domain, [("id", "in", list(parent_ids))]])
                parent_ids = set(parent_model.search(domain).ids)
            return parent_ids or set()
        parent_ids = set()
        for line in lines:
            parent_ids |= set(parent_model.search(line._get_condition_domain()).ids)
        return parent_ids

    def _get_duplicate_domain(self):
        self.ensure_one()
        if not self.duplicate_group_by_line_ids:
            raise UserError(_("Add at least one Duplicate Group By line."))
        groupby = [line._get_group_by_value() for line in self.duplicate_group_by_line_ids]
        model = self.env[self.main_model]
        try:
            rows = model.read_group(
                domain=self._get_condition_domain(),
                fields=["id:count"],
                groupby=groupby,
                lazy=False,
            )
        except Exception:
            return self._get_duplicate_domain_python()

        matching_domains = [
            row["__domain"]
            for row in rows
            if self._compare_count(row.get("__count", row.get("id_count", 0))) and row.get("__domain")
        ]
        if not matching_domains:
            return [("id", "in", [])]
        matching_records = model.search(expression.OR(matching_domains))
        return [("id", "in", matching_records.ids)]

    def _get_duplicate_domain_python(self):
        self.ensure_one()
        records = self.env[self.main_model].search(self._get_condition_domain())
        grouped_records = defaultdict(lambda: self.env[self.main_model])
        for record in records:
            grouped_records[self._get_duplicate_key(record)] |= record
        matching_records = self.env[self.main_model]
        for grouped in grouped_records.values():
            if self._compare_count(len(grouped)):
                matching_records |= grouped
        return [("id", "in", matching_records.ids)]

    def _get_duplicate_key(self, record):
        key = []
        for line in self.duplicate_group_by_line_ids:
            value = record[line.field_id.name]
            if line.date_interval and isinstance(value, (date, datetime)):
                value = self._date_interval_value(value, line.date_interval)
            elif hasattr(value, "ids"):
                value = tuple(value.ids)
            key.append(value)
        return tuple(key)

    def _date_interval_value(self, value, interval):
        if interval == "year":
            return value.year
        if interval == "month":
            return (value.year, value.month)
        if interval == "week":
            return value.isocalendar()[:2]
        if interval == "quarter":
            return (value.year, ((value.month - 1) // 3) + 1)
        if interval == "day":
            return value
        return value

    def _compare_count(self, count):
        operator = self.duplicate_count_operator
        expected = self.duplicate_count
        if operator == ">":
            return count > expected
        if operator == ">=":
            return count >= expected
        if operator == "=":
            return count == expected
        if operator == "!=":
            return count != expected
        if operator == "<":
            return count < expected
        if operator == "<=":
            return count <= expected
        return False

    def _check_model_available(self, model_name):
        if not model_name or model_name not in self.env:
            raise UserError(_("Model %s is not available in this database.") % (model_name or ""))

    def _get_group_by_context(self):
        self.ensure_one()
        group_by = []
        for line in self.group_by_line_ids:
            group_by.append(line._get_group_by_value())
        return group_by

    def action_apply_filter(self):
        self.ensure_one()
        domain = self._build_action_domain()
        context = dict(self.env.context)
        group_by = self._get_group_by_context()
        if group_by:
            context["group_by"] = group_by
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self.main_model,
            "view_mode": "list,kanban,pivot,graph,form",
            "views": [(False, "list"), (False, "kanban"), (False, "pivot"), (False, "graph"), (False, "form")],
            "domain": domain,
            "context": context,
            "target": "current",
        }

    def _get_native_favorite_name(self):
        self.ensure_one()
        return _("Advanced: %s") % self.name

    @api.model
    def _cleanup_odoo_favorites(self):
        """Remove legacy native favorites; the custom menu is the single source."""
        IrFilters = self.env["ir.filters"].sudo()
        advanced_filters = self.sudo().search([])
        native_filters = advanced_filters.mapped("ir_filter_id").sudo()

        names_by_model = defaultdict(list)
        for advanced_filter in advanced_filters.filtered("main_model"):
            names_by_model[advanced_filter.main_model].append(advanced_filter._get_native_favorite_name())

        for model_name, favorite_names in names_by_model.items():
            native_filters |= IrFilters.search(
                [
                    ("model_id", "=", model_name),
                    ("name", "in", favorite_names),
                ]
            )

        if native_filters:
            native_filters.unlink()
        advanced_filters.filtered("ir_filter_id").with_context(advanced_filter_skip_favorite_sync=True).write(
            {"ir_filter_id": False}
        )
        return True

    def _sync_odoo_favorites(self):
        return self._cleanup_odoo_favorites()

    @api.model
    def action_create_for_model(self, model_name):
        model = self.env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
        if not model:
            raise UserError(_("Model %s is not available in this database.") % (model_name or ""))
        return {
            "type": "ir.actions.act_window",
            "name": _("New Advanced Filter"),
            "res_model": "advanced.filter",
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_main_model_id": model.id,
                "default_relation_mode": "direct",
            },
        }

    @api.model
    def get_filters_for_model(self, model_name):
        filters = self.search(
            [
                ("main_model", "=", model_name),
                "|",
                ("user_id", "=", self.env.uid),
                ("is_shared", "=", True),
            ]
        )
        return [
            {
                "id": advanced_filter.id,
                "name": advanced_filter.name,
                "domain": advanced_filter.computed_domain,
                "is_default": advanced_filter.is_default,
                "is_shared": advanced_filter.is_shared,
                "user_id": advanced_filter.user_id.id,
                "is_owner": advanced_filter.user_id.id == self.env.uid,
            }
            for advanced_filter in filters
        ]

    def action_open_filter_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "advanced.filter",
            "res_id": self.id,
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "new",
        }

    def action_refresh_result_count(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Advanced Filter"),
                "message": _("%s record(s)") % self.result_count,
                "type": "info",
                "sticky": False,
            },
        }

    @api.model
    def save_filter(self, vals):
        vals["user_id"] = self.env.uid
        advanced_filter = self.create(vals)
        return {"id": advanced_filter.id, "name": advanced_filter.name}

    @api.model
    def delete_filter(self, filter_id):
        advanced_filter = self.browse(filter_id).exists()
        if not advanced_filter:
            return {"error": "Filter not found"}
        if advanced_filter.user_id.id != self.env.uid:
            return {"error": "You can only delete your own filters"}
        advanced_filter.unlink()
        return {"success": True}

    @api.model
    def get_model_fields(self, model_name):
        if model_name not in self.env:
            return []
        fields_data = []
        for name, field in self.env[model_name]._fields.items():
            if name.startswith("_"):
                continue
            field_info = {
                "name": name,
                "string": field.string,
                "type": field.type,
                "is_relational": field.type in ("many2one", "one2many", "many2many"),
            }
            if field.type in ("many2one", "one2many", "many2many"):
                field_info["relation"] = field.comodel_name
            fields_data.append(field_info)
        return sorted(fields_data, key=lambda item: item["string"] or item["name"])

    @api.model
    def build_domain(self, conditions, logic="AND"):
        domain = []
        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")
            if field and operator:
                domain.append((field, operator, value))
        if logic == "OR" and len(domain) > 1:
            return expression.OR([[leaf] for leaf in domain])
        return expression.AND([[leaf] for leaf in domain])


class AdvancedFilterLine(models.Model):
    _name = "advanced.filter.line"
    _description = "Advanced Filter Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    filter_id = fields.Many2one("advanced.filter", required=True, ondelete="cascade")
    condition_model_id = fields.Many2one(
        "ir.model",
        string="Condition Model",
        compute="_compute_condition_model_id",
        store=True,
    )
    condition_model = fields.Char(
        string="Condition Model Technical Name",
        compute="_compute_condition_model",
        store=True,
    )
    condition_domain = fields.Char(
        string="Domain Filter",
        default="[]",
        required=True,
        help="Native Odoo domain for this filter line.",
    )
    condition_display = fields.Char(string="Condition", compute="_compute_condition_display")

    @api.depends(
        "filter_id.main_model_id",
        "filter_id.related_model_id",
        "filter_id.relation_mode",
        "filter_id.relation_field_model",
    )
    def _compute_condition_model_id(self):
        for line in self:
            if line.filter_id.relation_mode == "direct":
                line.condition_model_id = line.filter_id.main_model_id
            elif line.filter_id.relation_mode in ("child_to_parent", "child_parent_child") and line.filter_id.relation_field_model:
                line.condition_model_id = self.env["ir.model"].search([("model", "=", line.filter_id.relation_field_model)], limit=1)
            else:
                line.condition_model_id = line.filter_id.related_model_id

    @api.depends("condition_model_id")
    def _compute_condition_model(self):
        for line in self:
            line.condition_model = line.condition_model_id.model

    def _has_condition_domain(self):
        self.ensure_one()
        raw_domain = (self.condition_domain or "").strip()
        return raw_domain not in ("", "[]")

    def _get_condition_domain(self):
        self.ensure_one()
        raw_domain = (self.condition_domain or "[]").strip() or "[]"
        try:
            domain = literal_eval(raw_domain)
        except (ValueError, SyntaxError) as error:
            raise UserError(_("Line domain filter is not valid.")) from error
        if not isinstance(domain, list):
            raise UserError(_("Line domain filter must be a list domain."))
        try:
            return expression.normalize_domain(domain)
        except (AssertionError, ValueError, TypeError) as error:
            raise UserError(_("Line domain filter is not valid.")) from error

    @api.depends("condition_domain")
    def _compute_condition_display(self):
        for line in self:
            line.condition_display = line.condition_domain or "[]"

    def action_open_condition(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("View/Edit Condition"),
            "res_model": "advanced.filter.line",
            "res_id": self.id,
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "new",
        }

    @api.constrains("condition_domain")
    def _check_condition_domain(self):
        for line in self:
            line._get_condition_domain()


class AdvancedFilterGroupBy(models.Model):
    _name = "advanced.filter.group.by"
    _description = "Advanced Filter Group By"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    filter_id = fields.Many2one("advanced.filter", required=True, ondelete="cascade")
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        required=True,
        domain="[('model_id', '=', parent.main_model_id), ('ttype', 'not in', ('binary', 'one2many', 'many2many'))]",
        ondelete="cascade",
    )
    date_interval = fields.Selection(
        [("day", "Day"), ("week", "Week"), ("month", "Month"), ("quarter", "Quarter"), ("year", "Year")],
        string="Date Interval",
    )

    def _get_group_by_value(self):
        self.ensure_one()
        if self.date_interval and self.field_id.ttype in ("date", "datetime"):
            return "%s:%s" % (self.field_id.name, self.date_interval)
        return self.field_id.name


class AdvancedFilterDuplicateGroupBy(models.Model):
    _name = "advanced.filter.duplicate.group.by"
    _description = "Advanced Filter Duplicate Group By"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    filter_id = fields.Many2one("advanced.filter", required=True, ondelete="cascade")
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        required=True,
        domain="[('model_id', '=', parent.main_model_id), ('ttype', 'not in', ('binary', 'one2many', 'many2many'))]",
        ondelete="cascade",
    )
    date_interval = fields.Selection(
        [("day", "Day"), ("week", "Week"), ("month", "Month"), ("quarter", "Quarter"), ("year", "Year")],
        string="Date Interval",
    )

    def _get_group_by_value(self):
        self.ensure_one()
        if self.date_interval and self.field_id.ttype in ("date", "datetime"):
            return "%s:%s" % (self.field_id.name, self.date_interval)
        return self.field_id.name
