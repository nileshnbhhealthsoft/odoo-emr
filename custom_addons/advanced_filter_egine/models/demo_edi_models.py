# -*- coding: utf-8 -*-

from odoo import fields, models


class DemoEdiClaim(models.Model):
    _name = "edi.claim"
    _description = "Claim"
    _order = "service_date desc, patient_control_number, payment_date asc"
    _rec_name = "claim_number"

    claim_number = fields.Char(index=True)
    payer_control_number = fields.Char(index=True)
    patient_control_number = fields.Char(index=True)
    patient_ref = fields.Char()
    resubmitted = fields.Selection(selection=[("yes", "Yes")], string="Resubmitted")
    record_type = fields.Char(string="Record Type")

    service_date = fields.Date()
    payment_date = fields.Date()
    production_date = fields.Date()
    charge_amount = fields.Float(string="Charge Amount")
    payment_amount = fields.Float(string="Payment Amount")
    payment_amount_avg = fields.Float(string="Payment Amount (AVG)")
    patient_responsibility_amount = fields.Float(string="Patient Responsibility Amount")
    total_payment_amount = fields.Float(string="Total Payment Amount")
    total_adj_amount = fields.Float(string="Total Adj Amount")
    fully_paid_tolerance = fields.Float(string="Fully Paid Tolerance", default=0.01)
    payment_percentage = fields.Float(string="Payment % of Charge", digits=(16, 2))
    claim_group_sort_pct = fields.Float(string="Group Net % Paid", index=True)

    claim_status_text = fields.Char(string="Claim Status")
    claim_filing_indicator = fields.Char()
    credit_debit_flag = fields.Char()
    payment_method = fields.Char()
    receiver_account_number = fields.Char()
    facility_type = fields.Char()
    frequency_type = fields.Char()
    payer_type = fields.Char(string="Payer Type", index=True)
    claim_bucket = fields.Selection(
        selection=[
            ("0_claim", "Zero Payment"),
            ("less_38", "Under 38% of Charge"),
            ("more_38", ">= 38% of Charge"),
        ],
        string="Payment Bucket",
        index=True,
    )

    transaction_control_number = fields.Char()
    check_eft_trace_number = fields.Char()
    payer_ein = fields.Char()

    payer_name = fields.Char()
    payee_identifier = fields.Char()
    payee_name = fields.Char()
    payee_address_line = fields.Char()
    payee_address_line2 = fields.Char()
    payee_city = fields.Char()
    payee_state = fields.Char()
    payee_zip = fields.Char()

    service_provider_identifier = fields.Char()
    service_provider_last_name = fields.Char()
    service_provider_first_name = fields.Char()

    patient_last_name = fields.Char()
    patient_first_name = fields.Char()
    patient_dob = fields.Date(string="Patient DOB")
    patient_age = fields.Char(string="Patient Age")
    patient_age_years = fields.Integer(string="Patient Age (Years)")
    patient_age_months = fields.Integer(string="Patient Age (Months)")
    patient_identification_type = fields.Char()
    patient_identifier = fields.Char()

    service_ids = fields.One2many("edi.service", "claim_id", string="Services")

    comment = fields.Text(string="Comments")
    comment_type = fields.Selection(
        string="Comments Visibility",
        selection=[("yes", "With Comment"), ("no", "Without Comment")],
    )
    encounter_id = fields.Integer(string="Encounter ID")
    name = fields.Char(index=True)
    claim_count_by_id = fields.Integer(string="Multiple Claims By ID")
    claim_count = fields.Integer(string="Multiple Claims")
    insurer_count = fields.Integer(string="Multiple Insurances")
    row_no = fields.Integer(string="Row #", index=True)
    sequence_in_visit = fields.Integer(string="Visit Seq #", index=True)

    is_first_claim = fields.Boolean(string="First 835 for Visit", index=True)
    is_latest_claim = fields.Boolean(string="Latest 835 for Visit", index=True)
    is_zero_payment = fields.Boolean(string="$0 Payment", index=True)
    is_initial_zero = fields.Boolean(string="Initial $0", index=True)
    is_recovery = fields.Boolean(string="Recovery (Paid after $0)", index=True)
    is_open_zero = fields.Boolean(string="Open $0 (No Later Payment)", index=True)
    zero_flow_state = fields.Selection(
        selection=[
            ("zero_claims", "$0 Claims"),
            ("followup", "FollowUP"),
            ("zero_to_paid", "$0 -> PAID"),
            ("followup_partial", "Partially Paid Claim to Fix"),
            ("fully_correct", "New 835 for Resubmitted partially paid"),
        ],
        string="Zero / PaidFix State (My Work)",
        index=True,
    )
    exclude_from_zero_flow_state = fields.Boolean(string="Exclude from Zero flow State", default=False)

    was_added_to_fix = fields.Boolean(string="Was Added To Fix")
    paid_fix_flag = fields.Boolean(string="Paid Claim to Fix")
    paid_fix_added = fields.Boolean(string="Paid to Fix")
    paid_fix_category = fields.Selection(
        selection=[
            ("followup_partial", "Partially Paid Claim to Fix"),
            ("fully_correct", "New 835 for Resubmitted partially paid"),
        ],
        string="Fix Sub-Category",
        index=True,
    )
    paid_fix_reason = fields.Text(string="AddtoFix due to")
    paid_fix_added_on = fields.Datetime(string="Paid-Fix Added On")
    zero_flow_state_updated_on = fields.Datetime(string="Zero Flow State Updated on")
    same_claim = fields.Char()


class DemoEdiService(models.Model):
    _name = "edi.service"
    _description = "Claim Services"
    _order = "claim_id, line_no, id"
    _rec_name = "cpt_code"

    claim_id = fields.Many2one("edi.claim", ondelete="cascade", index=True, string="Claim")
    record_type = fields.Char(string="Record Type")

    line_no = fields.Integer(index=True)
    row_no = fields.Integer(string="Row # in Payer Group", index=True)
    line_control_number = fields.Char(index=True)

    cpt_code = fields.Char(size=10, index=True, string="CPT Code")
    cpt_type = fields.Selection(
        selection=[
            ("well_visit", "Well Visit"),
            ("sick_visit", "Sick Visit"),
            ("diagnostic_test", "Diagnostic Test"),
        ],
        string="Type of CPT",
    )
    revenue_code = fields.Char()
    modifier1 = fields.Char(string="Modifier 1")
    modifier2 = fields.Char(string="Modifier 2")
    modifier3 = fields.Char(string="Modifier 3")
    modifier4 = fields.Char(string="Modifier 4")
    original_procedure_code = fields.Char()

    charge_amount = fields.Float(string="Charge Amount")
    paid_amount = fields.Float(string="Paid Amount")
    unit_count = fields.Integer(default=0, string="Units")

    date_start = fields.Date(string="Service Date From")
    date_end = fields.Date(string="Service Date To")

    icd_10_set = fields.Boolean(string="ICD-10 Set", default=False)
    icd_10_skip = fields.Boolean(string="ICD-10 Skip", default=False)
    icd_10_procedures_mismatch = fields.Boolean(string="ICD-10 Procedures Mismatch", default=False)
    icd_10 = fields.Json(string="ICD-10")
    icd_10_codes = fields.Text(string="ICD-10 Codes")
    icd_10_claims = fields.Html(string="ICD-10 Claims")
    icd10_description = fields.Html(string="ICD-10 Description")

    group_codes_csv = fields.Char(string="CAS Group Codes")
    comment = fields.Text(string="Comments")
    carc_codes_csv = fields.Char(string="CARC Codes")
    carc_code1 = fields.Char()
    carc_code1_excluded = fields.Boolean()
    carc_code2 = fields.Char()
    carc_code2_excluded = fields.Boolean()
    carc_desc1 = fields.Html()
    carc_desc2 = fields.Html()
    carc_description_joined = fields.Html(string="CARC Description")
    rarc_csv = fields.Char(string="RARC Codes")
    rarc_code1 = fields.Char()
    rarc_code1_excluded = fields.Boolean()
    rarc_code2 = fields.Char()
    rarc_code2_excluded = fields.Boolean()
    rarc_desc1 = fields.Html()
    rarc_desc2 = fields.Html()
    rarc_description_joined = fields.Html(string="RARC Description")
    sarts_csv = fields.Char()
    sarts1 = fields.Char()
    sarts2 = fields.Char()
    rarts1 = fields.Char()
    rarts2 = fields.Char()
    service_description = fields.Char()
    service_description_display = fields.Html(string="Description", sanitize=True)
    sarts_description_1 = fields.Char()
    sarts_description_2 = fields.Char()
    rarts_description_1 = fields.Char()
    rarts_description_2 = fields.Char()
    sort_key = fields.Integer()

    payment_date = fields.Date(string="Payment Date", index=True)
    production_date = fields.Date(string="Production Date")
    payer_name = fields.Char(string="Payer Name")
    payer_type = fields.Char(string="Payer Type", index=True)
    service_provider_identifier = fields.Char(string="Service Provider Identifier", index=True)
    service_provider_last_name = fields.Char(string="Service Provider Last Name")
    payer_control_number = fields.Char(string="Payer Control Number | CLAIM ID", index=True)
    claim_payment_amount = fields.Float(string="Claim Payment Amount")
    claim_charge_amount = fields.Float(string="Claim Charge Amount")
    patient_control_number = fields.Char(string="Patient Control Number")
    patient_identification_type = fields.Char(string="Patient Identification Type")
    patient_identifier = fields.Char(string="Patient Identifier")
    patient_last_name = fields.Char(string="Patient Last Name")
    patient_first_name = fields.Char(string="Patient First Name")
    patient_dob = fields.Date(string="Patient DOB")
    patient_age = fields.Char(string="Patient Age")
    patient_age_years = fields.Integer(string="Patient Age (Years)")
    patient_age_months = fields.Integer(string="Patient Age (Months)")
    claim_status_text = fields.Char(string="Claim Status")
    patient_responsibility_amount = fields.Float(string="Patient Responsibility Amount")
    claim_filing_indicator = fields.Char()
    pat_id = fields.Integer(string="Patient Internal ID")
    has_debit = fields.Boolean(string="Outstanding Balance")
    encounter_id = fields.Integer(string="Encounter ID")
    credit_debit_flag = fields.Char()
    payment_method = fields.Char()
    receiver_account_number = fields.Char()
    payer_ein = fields.Char()
    total_adj_amount = fields.Float(string="Total Adj Amount")
    payee_identifier = fields.Char()
    payee_name = fields.Char()
    payee_address_line = fields.Char()
    payee_address_line2 = fields.Char()
    payee_city = fields.Char()
    payee_state = fields.Char()
    payee_zip = fields.Char()
    claim_net_paid_pct = fields.Float(string="Net % Paid vs Gross Billed", digits=(16, 2))
    claim_bucket = fields.Selection(
        selection=[
            ("0_claim", "Zero Payment"),
            ("less_38", "Under 38% of Charge"),
            ("more_38", ">= 38% of Charge"),
        ],
        string="Payment Bucket",
        index=True,
    )
    payment_percentage = fields.Float(string="Payment % of Charge", digits=(16, 2))
    cpt_price = fields.Float(string="CPT Price")
    paid_less = fields.Char()
    already_paid = fields.Selection(
        string="CPT Already Paid",
        selection=[("yes", "Yes"), ("no", "No")],
    )
    claim_custom_group = fields.Html(string="Claim Group", sanitize=False)
    send_to_paid_fix = fields.Boolean(string="Flag Line -> Paid Claim to Fix")
    encounter_paid = fields.Selection(
        selection=[("yes", "Yes"), ("no", "No")],
        string="Encounter PAID",
        index=True,
    )
