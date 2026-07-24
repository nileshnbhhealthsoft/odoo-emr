# -*- coding: utf-8 -*-

import logging
from ast import literal_eval
from collections import defaultdict
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class AdvancedFilter(models.Model):
    _name = "advanced.filter"
    _description = "Advanced Filter Engine"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
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
    is_shared = fields.Boolean(string="Shared Filter", default=False, help="Visible to every user.")
    shared_user_ids = fields.Many2many(
        "res.users",
        "advanced_filter_shared_user_rel",
        "filter_id",
        "user_id",
        string="Shared With",
        help="Specific users this filter is visible to (in addition to the owner).",
    )
    is_default = fields.Boolean(
        string="Default Filter",
        default=False,
        help="Applied automatically when opening the target model. Synchronized "
        "to a native Odoo favorite.",
    )
    ir_filter_id = fields.Many2one(
        "ir.filters",
        string="Native Default Favorite",
        readonly=True,
        copy=False,
        ondelete="set null",
        help="Native favorite kept in sync for default filters, so they apply "
        "automatically when the view opens.",
    )
    condition_summary = fields.Text(string="Readable Conditions", compute="_compute_condition_summary")
    computed_domain = fields.Char(string="Computed Domain", compute="_compute_computed_domain")
    result_count = fields.Integer(string="Record Count", compute="_compute_result_count")
    comment_ids = fields.One2many("advanced.filter.comment", "filter_id", string="Comments")
    comment_count = fields.Integer(string="Comment Count", compute="_compute_comment_summary")
    latest_comment = fields.Char(string="Latest Comment", compute="_compute_comment_summary")
    draft_comment = fields.Char(
        string="Comment",
        compute="_compute_comment_summary",
        inverse="_inverse_draft_comment",
    )

    @api.depends("comment_ids.body", "comment_ids.comment_date", "comment_ids.user_id")
    def _compute_comment_summary(self):
        for advanced_filter in self:
            comments = advanced_filter.comment_ids.sorted("comment_date", reverse=True)
            advanced_filter.comment_count = len(comments)
            if comments:
                latest = comments[0]
                advanced_filter.latest_comment = "%s: %s" % (latest.user_id.name or "", latest.body or "")
                advanced_filter.draft_comment = latest.body or False
            else:
                advanced_filter.latest_comment = False
                advanced_filter.draft_comment = False

    def _inverse_draft_comment(self):
        for advanced_filter in self:
            body = (advanced_filter.draft_comment or "").strip()
            advanced_filter._cache["draft_comment"] = body or False
            if not body:
                continue
            latest = advanced_filter.comment_ids.sorted("comment_date", reverse=True)[:1]
            latest_body = latest.body.strip() if latest and latest.body else ""
            if body == latest_body:
                continue
            self.env["advanced.filter.comment"].create(
                {
                    "filter_id": advanced_filter.id,
                    "body": body,
                }
            )

    def action_open_comments(self):
        return False

    def action_send_draft_comment(self):
        self._inverse_draft_comment()
        return True

    @api.depends("main_model", "relation_mode")
    def _compute_relation_candidate_model_ids(self):
        IrModel = self.env["ir.model"]
        IrModelFields = self.env["ir.model.fields"]
        # Only stored many2one fields can be traversed in search domains, and
        # wizards/mixins make no sense as filter relations.
        m2o_domain = [("ttype", "=", "many2one"), ("store", "=", True)]
        for advanced_filter in self:
            candidate_models = IrModel.browse()
            if advanced_filter.main_model and advanced_filter.relation_mode == "child_to_parent":
                relation_fields = IrModelFields.search(
                    m2o_domain + [("relation", "=", advanced_filter.main_model)]
                )
                candidate_models = IrModel.search(
                    [("model", "in", relation_fields.mapped("model")), ("transient", "=", False)]
                )
            elif advanced_filter.main_model and advanced_filter.relation_mode == "parent_to_child":
                relation_fields = IrModelFields.search(
                    m2o_domain + [("model", "=", advanced_filter.main_model), ("relation", "!=", False)]
                )
                candidate_models = IrModel.search(
                    [("model", "in", relation_fields.mapped("relation")), ("transient", "=", False)]
                )
            elif advanced_filter.main_model and advanced_filter.relation_mode == "child_parent_child":
                parent_fields = IrModelFields.search(
                    m2o_domain + [("model", "=", advanced_filter.main_model), ("relation", "!=", False)]
                )
                relation_fields = IrModelFields.search(
                    m2o_domain + [("relation", "in", parent_fields.mapped("relation"))]
                )
                candidate_models = IrModel.search(
                    [("model", "in", relation_fields.mapped("model")), ("transient", "=", False)]
                )
            advanced_filter.relation_candidate_model_ids = candidate_models.filtered(
                lambda ir_model: ir_model.model in self.env
                and not self.env[ir_model.model]._abstract
            )

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
                advanced_filter.computed_domain = repr(advanced_filter._build_action_domain())
            except (UserError, ValidationError, ValueError, TypeError, KeyError):
                advanced_filter.computed_domain = "[]"

    @api.depends("computed_domain")
    def _compute_result_count(self):
        for advanced_filter in self:
            try:
                advanced_filter.result_count = self.env[advanced_filter.main_model].search_count(
                    advanced_filter._build_action_domain()
                )
            except (UserError, ValidationError, ValueError, TypeError, KeyError):
                advanced_filter.result_count = 0

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
            separator = _(" AND ") if advanced_filter.related_match_mode == "all" else _(" OR ")
            prefix = _("NOT matching: ") if advanced_filter.related_match_mode == "none" else ""
            advanced_filter.condition_summary = prefix + separator.join(lines.mapped("condition_display"))

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
        return self._combine_domains_by_match_mode([line._get_condition_domain() for line in lines])

    def _combine_domains_by_match_mode(self, domains):
        """Combine sub-domains according to related_match_mode.

        all -> AND, any -> OR, none -> NOT(OR): purely symbolic, no record
        ids are materialized.
        """
        self.ensure_one()
        if not domains:
            return []
        if self.related_match_mode == "any":
            return expression.OR(domains)
        if self.related_match_mode == "none":
            return ["!"] + expression.normalize_domain(expression.OR(domains))
        return expression.AND(domains)

    def _get_valid_condition_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line._has_condition_domain()).sorted(lambda line: (line.sequence, line.id))

    def _build_action_domain(self):
        self.ensure_one()
        self._check_model_available(self.main_model)

        if self.relation_mode == "direct" and self.duplicate_detection:
            return self._get_duplicate_domain()

        if self.relation_mode != "direct":
            self._check_model_available(self.related_model)
            if not self._is_relation_config_ready():
                return []
            self._validate_relation_field()

        lines = self._get_valid_condition_lines()
        if not lines:
            # No conditions means no restriction, whatever the match mode.
            return []

        symbolic_domain = self._build_symbolic_domain(lines)
        if symbolic_domain is not None:
            return symbolic_domain

        # Fallback (no usable inverse One2many): materialize matching ids.
        main_ids = self._get_matching_main_record_ids()
        operator = "not in" if self.related_match_mode == "none" else "in"
        return [("id", operator, list(main_ids))]

    def _build_symbolic_domain(self, lines):
        """Build a symbolic domain using the `any` operator, or None.

        Symbolic domains stay small, evaluate in a single SQL query and keep
        returning fresh results after data changes, unlike the id
        materialization fallback. Returns None when the setup cannot be
        expressed symbolically (relational modes traversing child conditions
        without an inverse One2many field on the parent model).
        """
        self.ensure_one()
        line_domains = [line._get_condition_domain() for line in lines]

        if self.relation_mode == "direct":
            return self._combine_domains_by_match_mode(line_domains)

        if self.relation_mode == "child_to_parent":
            if self.relation_field_id.model == self.main_model:
                # Reversed setup: the condition lines apply to the main model.
                return self._combine_domains_by_match_mode(line_domains)
            children_field = self._get_inverse_o2m_field_name(
                self.main_model, self.related_model, self.relation_field_id.name
            )
            if not children_field:
                return None
            return self._combine_domains_by_match_mode(
                [[(children_field, "any", domain)] for domain in line_domains]
            )

        if self.relation_mode == "parent_to_child":
            parent_field = self.relation_field_id.name
            if self.related_match_mode == "all":
                parent_domain = expression.AND(line_domains)
            else:
                parent_domain = expression.OR(line_domains)
            leaf = [(parent_field, "any", parent_domain)]
            if self.related_match_mode == "none":
                return ["!"] + expression.normalize_domain(leaf)
            return leaf

        if self.relation_mode == "child_parent_child":
            parent_model = self.result_relation_field_id.relation
            condition_children_field = self._get_inverse_o2m_field_name(
                parent_model, self.related_model, self.relation_field_id.name
            )
            if not condition_children_field:
                return None
            any_domains = [
                [(condition_children_field, "any", domain)] for domain in line_domains
            ]
            if self.related_match_mode in ("any", "none"):
                parent_domain = expression.OR(any_domains)
            else:
                parent_domain = expression.AND(any_domains)
            leaf = [(self.result_relation_field_id.name, "any", parent_domain)]
            if self.related_match_mode == "none":
                return ["!"] + expression.normalize_domain(leaf)
            return leaf

        return None

    def _get_inverse_o2m_field_name(self, parent_model, child_model, child_field_name):
        """Find the One2many on parent_model whose inverse is child_field_name."""
        if not parent_model or parent_model not in self.env:
            return None
        for field in self.env[parent_model]._fields.values():
            if (
                field.type == "one2many"
                and field.comodel_name == child_model
                and field.inverse_name == child_field_name
            ):
                return field.name
        return None

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
        except (UserError, ValidationError, ValueError, KeyError) as error:
            # Typically a non-stored field in the grouping. The Python
            # fallback loads every matching record, so make it visible.
            _logger.warning(
                "Advanced filter %s (id %s): SQL grouping failed (%s), "
                "falling back to Python duplicate detection on %s.",
                self.name, self.id, error, self.main_model,
            )
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

    @api.model_create_multi
    def create(self, vals_list):
        advanced_filters = super().create(vals_list)
        advanced_filters._sync_default_native_favorite()
        return advanced_filters

    def write(self, vals):
        if isinstance(vals.get("draft_comment"), str):
            vals = dict(vals, draft_comment=vals["draft_comment"].strip())
        result = super().write(vals)
        if not self.env.context.get("advanced_filter_skip_native_sync"):
            self._sync_default_native_favorite()
        return result

    def unlink(self):
        native_favorites = self.sudo().mapped("ir_filter_id")
        result = super().unlink()
        native_favorites.unlink()
        return result

    def _sync_default_native_favorite(self):
        """Keep a native ir.filters favorite in sync for default filters.

        Native default favorites are loaded together with the search view, so
        the filter applies automatically when the view opens, at no extra
        RPC cost. Symbolic domains (see _build_symbolic_domain) stay valid as
        data changes.
        """
        IrFilters = self.env["ir.filters"].sudo()
        for advanced_filter in self.sudo():
            native = advanced_filter.ir_filter_id
            if not (advanced_filter.is_default and advanced_filter.active):
                if native:
                    advanced_filter.with_context(advanced_filter_skip_native_sync=True).write(
                        {"ir_filter_id": False}
                    )
                    native.unlink()
                continue
            try:
                domain = advanced_filter._build_action_domain()
            except (UserError, ValidationError, ValueError, KeyError):
                # Incomplete configuration: skip until it becomes valid.
                continue
            context = {}
            group_by = advanced_filter._get_group_by_context()
            if group_by:
                context["group_by"] = group_by
            native_vals = {
                "name": advanced_filter.name,
                "model_id": advanced_filter.main_model,
                "domain": repr(domain),
                "context": repr(context),
                "sort": "[]",
                "is_default": True,
                "user_id": False if advanced_filter.is_shared else advanced_filter.user_id.id,
            }
            if native:
                native.write(native_vals)
            else:
                native = IrFilters.create(native_vals)
                advanced_filter.with_context(advanced_filter_skip_native_sync=True).write(
                    {"ir_filter_id": native.id}
                )

    def _get_native_favorite_name(self):
        self.ensure_one()
        return _("Advanced: %s") % self.name

    @api.model
    def _cleanup_odoo_favorites(self):
        """Remove legacy native favorites created by older module versions."""
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
        advanced_filters.filtered("ir_filter_id").with_context(advanced_filter_skip_native_sync=True).write(
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
            "target": "new",
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
                "|",
                ("user_id", "=", self.env.uid),
                ("is_shared", "=", True),
                ("shared_user_ids", "in", self.env.uid),
            ]
        )
        return [
            {
                "id": advanced_filter.id,
                "name": advanced_filter.name,
                "sequence": advanced_filter.sequence,
                "is_default": advanced_filter.is_default,
                "is_shared": advanced_filter.is_shared
                or advanced_filter.user_id.id != self.env.uid,
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
        """Count matching records on demand; the count is intentionally not a
        computed field so opening/editing the form stays cheap."""
        self.ensure_one()
        count = self.env[self.main_model].search_count(self._build_action_domain())
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Advanced Filter"),
                "message": _("%s record(s)") % count,
                "type": "info",
                "sticky": False,
            },
        }

    @api.model
    def reorder_filters(self, filter_ids):
        position_by_id = {filter_id: index for index, filter_id in enumerate(filter_ids)}
        own_filters = self.browse(filter_ids).exists().filtered(
            lambda advanced_filter: advanced_filter.user_id.id == self.env.uid
        )
        for advanced_filter in own_filters:
            advanced_filter.sequence = (position_by_id[advanced_filter.id] + 1) * 10
        return True

    @api.model
    def delete_filter(self, filter_id):
        advanced_filter = self.browse(filter_id).exists()
        if not advanced_filter:
            return {"error": _("Filter not found")}
        if advanced_filter.user_id.id != self.env.uid:
            return {"error": _("You can only delete your own filters")}
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


class AdvancedFilterComment(models.Model):
    _name = "advanced.filter.comment"
    _description = "Advanced Filter Comment"
    _order = "comment_date desc, id desc"

    filter_id = fields.Many2one("advanced.filter", string="Filter", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    comment_date = fields.Datetime(
        string="Commented On",
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    body = fields.Text(string="Comment", required=True)

    def _format_comment_datetime(self, value):
        if not value:
            return ""
        timestamp = fields.Datetime.context_timestamp(self, value)
        return timestamp.strftime("%Y-%m-%d %H:%M")

    def _comment_payload(self):
        self.ensure_one()
        display_date = self.write_date if self.write_date and self.write_date != self.create_date else self.comment_date
        is_edited = False
        if self.write_date and self.create_date:
            is_edited = (self.write_date - self.create_date).total_seconds() > 1
        return {
            "id": self.id,
            "filter_id": self.filter_id.id,
            "user_id": self.user_id.id,
            "username": self.user_id.name or "",
            "comment": self.body or "",
            "created_at": self._format_comment_datetime(self.comment_date or self.create_date),
            "updated_at": self._format_comment_datetime(self.write_date),
            "display_date": self._format_comment_datetime(display_date),
            "is_edited": is_edited,
            "is_owner": self.user_id.id == self.env.uid,
        }

    @api.model
    def get_comments_by_filter(self, filter_id):
        advanced_filter = self.env["advanced.filter"].browse(filter_id).exists()
        if not advanced_filter:
            return []
        comments = self.search([("filter_id", "=", advanced_filter.id)], order="comment_date asc, id asc")
        return [comment._comment_payload() for comment in comments]

    @api.model
    def add_comment(self, filter_id, comment):
        body = (comment or "").strip()
        if not body:
            return {"error": _("Comment cannot be empty.")}
        advanced_filter = self.env["advanced.filter"].browse(filter_id).exists()
        if not advanced_filter:
            return {"error": _("Filter not found.")}
        new_comment = self.create(
            {
                "filter_id": advanced_filter.id,
                "body": body,
            }
        )
        return new_comment._comment_payload()

    @api.model
    def update_comment(self, comment_id, comment):
        body = (comment or "").strip()
        if not body:
            return {"error": _("Comment cannot be empty.")}
        existing_comment = self.browse(comment_id).exists()
        if not existing_comment:
            return {"error": _("Comment not found.")}
        if existing_comment.user_id.id != self.env.uid:
            return {"error": _("You can only edit your own comments.")}
        existing_comment.body = body
        return existing_comment._comment_payload()

    @api.model
    def delete_comment(self, comment_id):
        existing_comment = self.browse(comment_id).exists()
        if not existing_comment:
            return {"error": _("Comment not found.")}
        if existing_comment.user_id.id != self.env.uid:
            return {"error": _("You can only delete your own comments.")}
        existing_comment.sudo().unlink()
        return {"deleted": True, "id": comment_id}


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

    @api.depends("condition_domain", "condition_model")
    def _compute_condition_display(self):
        for line in self:
            line.condition_display = line._humanize_condition_domain()

    def _humanize_condition_domain(self):
        """Render the raw domain as a readable sentence, e.g.
        ``CPT Category Code is well_visit and Paid Amount > 0``.
        Falls back to the raw domain string when anything cannot be resolved.
        """
        self.ensure_one()
        raw_domain = (self.condition_domain or "[]").strip() or "[]"
        model_name = self.condition_model
        if not model_name or model_name not in self.env:
            return raw_domain
        try:
            tokens = list(expression.normalize_domain(literal_eval(raw_domain)))
        except (ValueError, SyntaxError, AssertionError, TypeError):
            return raw_domain
        if not tokens or tokens == [expression.TRUE_LEAF]:
            return ""
        try:
            text = self._humanize_domain_tokens(self.env[model_name], tokens)
        except Exception:  # noqa: BLE001 - display helper must never break reads
            return raw_domain
        # Drop the outermost parentheses for readability.
        if text.startswith("(") and text.endswith(")"):
            text = text[1:-1]
        return text or raw_domain

    def _humanize_domain_tokens(self, model, tokens):
        token = tokens.pop(0)
        if token == "&":
            left = self._humanize_domain_tokens(model, tokens)
            right = self._humanize_domain_tokens(model, tokens)
            return "(%s %s %s)" % (left, _("and"), right)
        if token == "|":
            left = self._humanize_domain_tokens(model, tokens)
            right = self._humanize_domain_tokens(model, tokens)
            return "(%s %s %s)" % (left, _("or"), right)
        if token == "!":
            return "%s %s" % (_("not"), self._humanize_domain_tokens(model, tokens))
        return self._humanize_domain_leaf(model, token)

    def _humanize_domain_leaf(self, model, leaf):
        field_path, operator, value = leaf
        if leaf == expression.TRUE_LEAF:
            return _("always")
        if leaf == expression.FALSE_LEAF:
            return _("never")

        labels = []
        current_model = model
        field = None
        for part in str(field_path).split("."):
            field = current_model._fields.get(part) if current_model is not None else None
            if field is None:
                return repr(leaf)
            labels.append(field.string or part)
            current_model = (
                self.env[field.comodel_name] if field.relational else None
            )
        field_label = " / ".join(labels)

        if operator in ("any", "not any"):
            sub_tokens = list(expression.normalize_domain(value))
            sub_text = self._humanize_domain_tokens(self.env[field.comodel_name], sub_tokens)
            pattern = _("%(field)s has a match: %(sub)s") if operator == "any" else _("%(field)s has no match: %(sub)s")
            return pattern % {"field": field_label, "sub": sub_text}

        if value is False and field.type != "boolean" and operator in ("=", "!="):
            return "%s %s" % (field_label, _("is not set") if operator == "=" else _("is set"))

        operator_label = {
            "=": _("is"),
            "!=": _("is not"),
            "ilike": _("contains"),
            "not ilike": _("does not contain"),
            "like": _("matches"),
            "=like": _("matches"),
            "=ilike": _("matches"),
            "in": _("is one of"),
            "not in": _("is not one of"),
            "child_of": _("is child of"),
            "parent_of": _("is parent of"),
        }.get(operator, operator)

        return "%s %s %s" % (field_label, operator_label, self._humanize_domain_value(field, value))

    def _humanize_domain_value(self, field, value):
        if isinstance(value, (list, tuple)):
            return ", ".join(self._humanize_domain_value(field, item) for item in value)
        if field.type == "boolean":
            return _("Yes") if value else _("No")
        if field.type == "selection":
            selection = dict(field._description_selection(self.env))
            return str(selection.get(value, value))
        if field.relational and isinstance(value, int):
            record = self.env[field.comodel_name].browse(value).exists()
            if record:
                return record.display_name
        return str(value)

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

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.filter_id._sync_default_native_favorite()
        return lines

    def write(self, vals):
        result = super().write(vals)
        self.filter_id._sync_default_native_favorite()
        return result

    def unlink(self):
        filters = self.filter_id
        result = super().unlink()
        filters._sync_default_native_favorite()
        return result


class AdvancedFilterGroupByBase(models.AbstractModel):
    _name = "advanced.filter.group.by.base"
    _description = "Advanced Filter Group By Base"
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
    field_type = fields.Selection(related="field_id.ttype", string="Field Type", readonly=True)
    date_interval = fields.Selection(
        [("day", "Day"), ("week", "Week"), ("month", "Month"), ("quarter", "Quarter"), ("year", "Year")],
        string="Date Interval",
    )

    def _get_group_by_value(self):
        self.ensure_one()
        if self.date_interval and self.field_id.ttype in ("date", "datetime"):
            return "%s:%s" % (self.field_id.name, self.date_interval)
        return self.field_id.name

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.filter_id._sync_default_native_favorite()
        return lines

    def write(self, vals):
        result = super().write(vals)
        self.filter_id._sync_default_native_favorite()
        return result

    def unlink(self):
        filters = self.filter_id
        result = super().unlink()
        filters._sync_default_native_favorite()
        return result


class AdvancedFilterGroupBy(models.Model):
    _name = "advanced.filter.group.by"
    _inherit = "advanced.filter.group.by.base"
    _description = "Advanced Filter Group By"


class AdvancedFilterDuplicateGroupBy(models.Model):
    _name = "advanced.filter.duplicate.group.by"
    _inherit = "advanced.filter.group.by.base"
    _description = "Advanced Filter Duplicate Group By"
