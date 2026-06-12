from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAdvancedFilterEngine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Filter = cls.env["advanced.filter"]
        cls.DataFilterWizard = cls.env["data.filter.wizard"]
        cls.IrModel = cls.env["ir.model"]
        cls.IrField = cls.env["ir.model.fields"]
        cls.claim_model = cls.IrModel.search([("model", "=", "edi.claim")], limit=1)
        cls.service_model = cls.IrModel.search([("model", "=", "edi.service")], limit=1)
        cls.claim_id_field = cls.IrField.search(
            [("model", "=", "edi.service"), ("name", "=", "claim_id")],
            limit=1,
        )
        cls.cpt_type_field = cls.IrField.search(
            [("model", "=", "edi.service"), ("name", "=", "cpt_type")],
            limit=1,
        )
        cls.payer_name_field = cls.IrField.search(
            [("model", "=", "edi.claim"), ("name", "=", "payer_name")],
            limit=1,
        )
        cls.claim_status_field = cls.IrField.search(
            [("model", "=", "edi.claim"), ("name", "=", "claim_status_text")],
            limit=1,
        )
        cls.paid_amount_field = cls.IrField.search(
            [("model", "=", "edi.service"), ("name", "=", "paid_amount")],
            limit=1,
        )

    def _create_filter(self, vals):
        return self.Filter.create({"name": "Test Filter", **vals})

    def _demo_claim_names(self, domain):
        records = self.env["edi.claim"].search(
            domain + [("patient_control_number", "in", ["TEST-A", "TEST-B", "TEST-C"])]
        )
        return set(records.mapped("claim_number"))

    def _demo_service_keys(self, domain):
        records = self.env["edi.service"].search(
            domain + [("patient_control_number", "in", ["TEST-A", "TEST-B", "TEST-C"])]
        )
        return set(records.mapped(lambda service: (service.claim_id.claim_number, service.cpt_type)))

    def test_child_to_parent_all_match(self):
        advanced_filter = self._create_filter(
            {
                "main_model_id": self.claim_model.id,
                "relation_mode": "child_to_parent",
                "related_model_id": self.service_model.id,
                "relation_field_id": self.claim_id_field.id,
                "related_match_mode": "all",
                "line_ids": [
                    (0, 0, {"condition_domain": repr([("cpt_type", "=", "well_visit")])}),
                    (0, 0, {"condition_domain": repr([("cpt_type", "=", "sick_visit")])}),
                ],
            }
        )

        self.assertEqual(self._demo_claim_names(advanced_filter._build_action_domain()), {"Claim A"})

    def test_child_to_parent_all_match_not_equal_excludes_related_value(self):
        advanced_filter = self._create_filter(
            {
                "main_model_id": self.claim_model.id,
                "relation_mode": "child_to_parent",
                "related_model_id": self.service_model.id,
                "relation_field_id": self.claim_id_field.id,
                "related_match_mode": "all",
                "line_ids": [
                    (0, 0, {"condition_domain": repr([("cpt_type", "=", "well_visit")])}),
                    (0, 0, {"condition_domain": repr([("cpt_type", "!=", "sick_visit")])}),
                ],
            }
        )

        self.assertEqual(self._demo_claim_names(advanced_filter._build_action_domain()), {"Claim A", "Claim B"})

    def test_related_match_mode_changes_result_without_clearing_lines(self):
        advanced_filter = self._create_filter(
            {
                "main_model_id": self.claim_model.id,
                "relation_mode": "child_to_parent",
                "related_model_id": self.service_model.id,
                "relation_field_id": self.claim_id_field.id,
                "related_match_mode": "any",
                "line_ids": [
                    (0, 0, {"condition_domain": repr([("cpt_type", "=", "well_visit")])}),
                    (0, 0, {"condition_domain": repr([("paid_amount", ">", 0)])}),
                ],
            }
        )

        self.assertEqual(
            self._demo_claim_names(advanced_filter._build_action_domain()),
            {"Claim A", "Claim B", "Claim C"},
        )
        self.assertEqual(len(advanced_filter.line_ids), 2)

        advanced_filter.related_match_mode = "all"
        self.assertEqual(self._demo_claim_names(advanced_filter._build_action_domain()), {"Claim A", "Claim B"})
        self.assertEqual(
            advanced_filter.line_ids.mapped("condition_domain"),
            [repr([("cpt_type", "=", "well_visit")]), repr([("paid_amount", ">", 0)])],
        )

        advanced_filter.related_match_mode = "none"
        self.assertFalse(self._demo_claim_names(advanced_filter._build_action_domain()))

    def test_condition_display_uses_selection_label(self):
        advanced_filter = self._create_filter(
            {
                "main_model_id": self.claim_model.id,
                "relation_mode": "child_to_parent",
                "related_model_id": self.service_model.id,
                "relation_field_id": self.claim_id_field.id,
                "line_ids": [
                    (0, 0, {"condition_domain": repr([("cpt_type", "=", "well_visit")])}),
                ],
            }
        )

        line = advanced_filter.line_ids
        self.assertIn("well_visit", line.condition_display)
        self.assertIn("well_visit", advanced_filter.condition_summary)

    def test_service_domain_supports_nested_groups(self):
        wizard = self.DataFilterWizard.create(
            {
                "model_id": self.service_model.id,
                "domain": repr(
                    [
                        "&",
                        "|",
                        ("cpt_type", "=", "well_visit"),
                        ("paid_amount", ">", 0),
                        "|",
                        ("cpt_type", "=", "sick_visit"),
                        ("paid_amount", "<=", 0),
                    ]
                ),
            }
        )

        self.assertEqual(
            self._demo_service_keys(wizard._get_domain()),
            {("Claim A", "sick_visit"), ("Claim C", "sick_visit")},
        )
        self.assertGreaterEqual(wizard.result_count, 2)

    def test_get_services_applies_current_service_domain(self):
        wizard = self.DataFilterWizard.create(
            {
                "model_id": self.service_model.id,
                "domain": repr([("cpt_type", "=", "well_visit"), ("paid_amount", ">", 0)]),
            }
        )

        action = wizard.action_open_records()
        self.assertEqual(action["res_model"], "edi.service")
        self.assertEqual(
            self._demo_service_keys(action["domain"]),
            {("Claim A", "well_visit"), ("Claim B", "well_visit")},
        )

    def test_parent_to_child(self):
        advanced_filter = self._create_filter(
            {
                "main_model_id": self.service_model.id,
                "relation_mode": "parent_to_child",
                "related_model_id": self.claim_model.id,
                "relation_field_id": self.claim_id_field.id,
                "line_ids": [
                    (0, 0, {"condition_domain": repr([("payer_name", "=", "CareSource")])}),
                    (0, 0, {"condition_domain": repr([("claim_status_text", "=", "Paid")])}),
                ],
            }
        )

        records = self.env["edi.service"].search(advanced_filter._build_action_domain())
        self.assertTrue(records)
        self.assertTrue(all(record.claim_id.payer_name == "CareSource" for record in records))
        self.assertTrue(all(record.claim_id.claim_status_text == "Paid" for record in records))

    def test_direct_any_line_domains(self):
        payer_name_field = self.IrField.search(
            [("model", "=", "edi.service"), ("name", "=", "payer_name")],
            limit=1,
        )
        advanced_filter = self._create_filter(
            {
                "main_model_id": self.service_model.id,
                "relation_mode": "direct",
                "related_match_mode": "all",
                "line_ids": [
                    (0, 0, {"condition_domain": repr(["|", ("cpt_type", "=", "well_visit"), ("cpt_type", "=", "sick_visit")])}),
                    (0, 0, {"condition_domain": repr([(payer_name_field.name, "=", "CareSource")])}),
                ],
            }
        )

        records = self.env["edi.service"].search(advanced_filter._build_action_domain())
        self.assertTrue(records)
        self.assertTrue(all(record.cpt_type in {"well_visit", "sick_visit"} for record in records))
        self.assertTrue(all(record.payer_name == "CareSource" for record in records))

    def test_child_parent_child_returns_all_services_for_matching_claim(self):
        advanced_filter = self._create_filter(
            {
                "main_model_id": self.service_model.id,
                "relation_mode": "child_parent_child",
                "related_model_id": self.service_model.id,
                "relation_field_id": self.claim_id_field.id,
                "result_relation_field_id": self.claim_id_field.id,
                "related_match_mode": "all",
                "line_ids": [
                    (0, 0, {"condition_domain": repr([("cpt_type", "=", "well_visit")])}),
                    (0, 0, {"condition_domain": repr([("cpt_type", "=", "sick_visit")])}),
                ],
            }
        )

        records = self.env["edi.service"].search(advanced_filter._build_action_domain())
        self.assertEqual(set(records.mapped("claim_id.claim_number")), {"Claim A"})
        self.assertEqual(set(records.mapped("cpt_type")), {"well_visit", "sick_visit", "diagnostic_test"})
