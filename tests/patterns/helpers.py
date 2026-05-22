"""Shared test helpers for intent-engine tests."""

from __future__ import annotations

import json


def valid_payments_json() -> str:
    """Mock LLM JSON response for valid-payments.md fixture."""
    return json.dumps(
        {
            "decisions": {
                "primary_region": "eu-central-1",
                "topology": "hub-spoke",
                "network_cidr": "10.0.0.0/16",
                "central_network_account": "Network",
                "hub_cidr": "10.0.0.0/20",
                "audit_retention_days": "2555",
                "centralized_logging": True,
                "egress_inspection": "none",
                "cicd_mode": "private",
                "cicd_placement": "shared-vpc",
            },
            "signal_decisions": {},
            "addons_suggested": [],
            "gaps": [],
            "contradictions": [],
            "ous": [
                {"name": "Security", "description": "Security baseline OU"},
                {"name": "Infrastructure", "description": "Infrastructure and shared services OU"},
                {"name": "Workloads/Prod", "description": "Production workloads OU"},
            ],
            "accounts": [
                {
                    "name": "Network",
                    "ou": "Infrastructure",
                    "description": "Central networking account",
                },
                {"name": "Audit", "ou": "Security", "description": "Audit and compliance account"},
                {"name": "LogArchive", "ou": "Security", "description": "Log archival account"},
                {
                    "name": "SharedServices",
                    "ou": "Infrastructure",
                    "description": "Shared services account",
                },
                {
                    "name": "PaymentsProd",
                    "ou": "Workloads/Prod",
                    "description": "Payments production account",
                },
            ],
            "workloads": [
                {
                    "name": "payments-api",
                    "target_account": "PaymentsProd",
                    "network_mode": "private",
                    "public_ingress": False,
                    "port": 8080,
                    "cpu": 512,
                    "memory": 1024,
                }
            ],
        }
    )


def invalid_design_json() -> str:
    """Mock LLM JSON response for invalid-design.md fixture."""
    return json.dumps(
        {
            "decisions": {
                "primary_region": "eu-central-1",
                "topology": "hub-spoke",
                "network_cidr": "10.0.0.0/16",
                "cicd_mode": "private",
            },
            "signal_decisions": {},
            "addons_suggested": [],
            "gaps": [
                {
                    "key": "central_network_account",
                    "reason": "hub-spoke requires Network account",
                    "suggestion": "Add central_network_account",
                },
                {
                    "key": "cicd_placement",
                    "reason": "private CI/CD requires placement",
                    "suggestion": "Add cicd_placement",
                },
            ],
            "contradictions": [],
            "workloads": [
                {
                    "name": "payments-api",
                    "target_account": "PaymentsProd",
                    "network_mode": "private",
                }
            ],
        }
    )
