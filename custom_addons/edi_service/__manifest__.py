{
    "name": "EDI Services",
    "version": "18.0.1.0.0",
    "category": "Healthcare",
    "summary": "EDI 835 Service Lines",
    "depends": [
        "base",
        "edi_claim",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/edi_service_views.xml",
    ],
    "installable": True,
    "application": True,
}