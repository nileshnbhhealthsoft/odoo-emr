# -*- coding: utf-8 -*-

import csv
import json
import logging
from pathlib import Path

from odoo import fields

_logger = logging.getLogger(__name__)


def _convert_value(field, value):
    value = (value or "").strip()
    if not value:
        return False
    if field.type == "integer":
        return int(float(value))
    if field.type in ("float", "monetary"):
        return float(value)
    if field.type == "date":
        return fields.Date.to_date(value)
    if field.type == "json":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return False
    return value


def _create_in_batches(model, rows, size=1000):
    for index in range(0, len(rows), size):
        model.create(rows[index:index + size])


def post_init_hook(env):
    module_dir = Path(__file__).resolve().parent
    data_dir = module_dir / "data"
    claim_csv = data_dir / "edi_claim_2025_2026.csv"
    service_csv = data_dir / "edi_service_2025_2026.csv"

    Claim = env["edi.claim"].sudo()
    Service = env["edi.service"].sudo()
    if Claim.search_count([("source_id", "!=", False)]) or Service.search_count([("source_claim_id", "!=", False)]):
        _logger.info("Advanced Filter claim demo data already exists; skipping CSV import.")
        return

    claim_rows = []
    with claim_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            values = {}
            source_id = row.pop("id", None)
            if source_id:
                values["source_id"] = int(source_id)
            for key, value in row.items():
                field = Claim._fields.get(key)
                if field:
                    values[key] = _convert_value(field, value)
            claim_rows.append(values)

    _create_in_batches(Claim, claim_rows)
    claim_by_source = {
        claim.source_id: claim.id
        for claim in Claim.search([("source_id", "!=", False)])
    }

    service_rows = []
    skipped = 0
    with service_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_claim_id = row.pop("claim_id", None)
            if not source_claim_id:
                skipped += 1
                continue
            source_claim_id = int(float(source_claim_id))
            claim_id = claim_by_source.get(source_claim_id)
            if not claim_id:
                skipped += 1
                continue
            values = {
                "source_claim_id": source_claim_id,
                "claim_id": claim_id,
            }
            for key, value in row.items():
                field = Service._fields.get(key)
                if field:
                    values[key] = _convert_value(field, value)
            service_rows.append(values)

    _create_in_batches(Service, service_rows)
    _logger.info(
        "Imported Advanced Filter claim demo data: %s claims, %s services, %s skipped services.",
        len(claim_rows),
        len(service_rows),
        skipped,
    )
