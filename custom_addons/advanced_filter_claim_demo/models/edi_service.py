from odoo import fields, models


class EdiService(models.Model):
    _name = "edi.service"
    _description = "EDI Service Line (835)"
    _rec_name = "cpt_code"

    source_claim_id = fields.Integer(index=True, readonly=True)
    claim_id = fields.Many2one("edi.claim", ondelete="cascade", index=True)

    line_no = fields.Integer()
    line_control_number = fields.Char(index=True)
    patient_control_number = fields.Char(index=True)
    pat_id = fields.Integer()

    cpt_code = fields.Char(size=10, index=True)
    cpt_type = fields.Char()
    revenue_code = fields.Char()
    modifier1 = fields.Char()
    modifier2 = fields.Char()
    modifier3 = fields.Char()
    modifier4 = fields.Char()
    original_procedure_code = fields.Char()
    unit_count = fields.Integer()

    charge_amount = fields.Float()
    paid_amount = fields.Float()

    date_start = fields.Date()
    date_end = fields.Date()
    payment_date = fields.Date()
    production_date = fields.Date()

    icd_10 = fields.Json()
    icd_10_codes = fields.Text()

    group_codes_csv = fields.Char()
    carc_codes_csv = fields.Char()
    carc_code1 = fields.Char()
    carc_code2 = fields.Char()
    rarc_csv = fields.Char()
    rarc_code1 = fields.Char()
    rarc_code2 = fields.Char()
    sarts1 = fields.Char()
    sarts2 = fields.Char()
    rarts1 = fields.Char()
    rarts2 = fields.Char()

    payer_name = fields.Char()
    payer_type = fields.Char()
    claim_status_text = fields.Char()
    claim_charge_amount = fields.Float()
    claim_payment_amount = fields.Float()
    payment_percentage = fields.Float(digits=(16, 2))

    service_provider_identifier = fields.Char()
    patient_age_years = fields.Integer()
    patient_age_months = fields.Integer()
