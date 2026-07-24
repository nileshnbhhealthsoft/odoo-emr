{
    "name": "Advanced Filter Claim Demo",
    "version": "18.0.1.0.0",
    "summary": "Claim and service line data for testing Advanced Filter",
    "author": "Client",
    "category": "Tools",
    "depends": ["advanced_filter_engine"],
    "data": [
        "security/ir.model.access.csv",
        "views/edi_claim_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
