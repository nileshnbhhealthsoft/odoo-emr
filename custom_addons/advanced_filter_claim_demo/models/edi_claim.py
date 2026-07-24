from odoo import fields, models


class EdiClaim(models.Model):
    _name = "edi.claim"
    _description = "EDI Claim (835)"
    _rec_name = "claim_number"

    source_id = fields.Integer(index=True, readonly=True)
    claim_number = fields.Char(index=True)
    payer_control_number = fields.Char(index=True)
    patient_control_number = fields.Char(index=True)

    service_date = fields.Date()
    payment_date = fields.Date()
    production_date = fields.Date()

    charge_amount = fields.Float()
    payment_amount = fields.Float()
    total_payment_amount = fields.Float()
    net_paid_pct = fields.Float(digits=(16, 2))
    payment_percentage = fields.Float(digits=(16, 2))
    fully_paid_tolerance = fields.Float()

    claim_status_text = fields.Char()
    facility_type = fields.Char()
    frequency_type = fields.Char()
    transaction_control_number = fields.Char()
    check_eft_trace_number = fields.Char()

    payer_name = fields.Char()
    payer_type = fields.Char()

    service_provider_identifier = fields.Char()
    service_provider_last_name = fields.Char()
    service_provider_first_name = fields.Char()

    services_count = fields.Integer()
    patient_age_years = fields.Integer()
    patient_age_months = fields.Integer()

    diagnosis_codes = fields.Text()

    service_ids = fields.One2many("edi.service", "claim_id")
