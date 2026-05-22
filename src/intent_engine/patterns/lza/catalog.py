"""LZA-specific catalog entries.

Registers known-good LZA decision sets with the global ConfigCatalog.
Imported for side effects by cli.py.
"""

from __future__ import annotations

from intent_engine.core.catalog import CatalogEntry, ConfigCatalog

_LZA_ENTRIES: list[CatalogEntry] = [
    CatalogEntry(
        name="lza-minimal",
        description="Bare minimum landing zone: region, single-vpc, audit retention",
        pattern="minimal",
        decisions={
            "primary_region": "eu-central-1",
            "topology": "single-vpc",
            "network_cidr": "10.0.0.0/16",
            "audit_retention_days": "2555",
        },
        notes={
            "architect": "Start here for 1-2 accounts, no compliance.",
            "engineer": "Produces org, accounts, global, security configs.",
        },
        tags=["starter", "minimal", "compliance-none"],
    ),
    CatalogEntry(
        name="lza-baseline",
        description="Standard AWS LZA with hub-spoke, security, CI/CD",
        pattern="baseline",
        decisions={
            "primary_region": "eu-central-1",
            "topology": "hub-spoke",
            "central_network_account": "Network",
            "network_cidr": "10.0.0.0/16",
            "hub_cidr": "10.0.0.0/20",
            "audit_retention_days": "2555",
            "centralized_logging": "true",
            "cicd_mode": "public",
            "egress_inspection": "none",
            "hybrid_required": "false",
        },
        notes={
            "architect": "For enterprises with 5+ accounts and standard security.",
            "engineer": "10 YAML files. No hybrid or egress inspection.",
        },
        tags=["standard", "enterprise", "hub-spoke"],
    ),
    CatalogEntry(
        name="lza-hybrid-enterprise",
        description="Baseline LZA with hybrid connectivity and enhanced security",
        pattern="hybrid-enterprise",
        decisions={
            "primary_region": "eu-central-1",
            "topology": "hub-spoke",
            "central_network_account": "Network",
            "network_cidr": "10.0.0.0/16",
            "hub_cidr": "10.0.0.0/20",
            "audit_retention_days": "2555",
            "centralized_logging": "true",
            "cicd_mode": "private",
            "cicd_placement": "SharedServices/BuildVPC",
            "egress_inspection": "required",
            "inspection_pattern": "centralized-nat",
            "inspection_vendor": "aws-network-firewall",
            "hybrid_required": "true",
            "hybrid_dns_model": "aws-resolver",
            "hybrid_ip_model": "rfc1918-only",
            "hybrid_on_prem_cidrs": "10.100.0.0/16,192.168.0.0/24",
        },
        notes={
            "architect": "For enterprises with on-prem and strict outbound inspection.",
            "engineer": "Includes Direct Connect, hybrid DNS, VPC endpoints, egress firewall.",
        },
        tags=["hybrid", "enterprise", "compliance", "on-prem"],
    ),
    CatalogEntry(
        name="lza-financial",
        description="Financial services with PCI-DSS, SOX, and payment segmentation",
        pattern="financial-services",
        decisions={
            "primary_region": "eu-central-1",
            "topology": "hub-spoke",
            "central_network_account": "Network",
            "network_cidr": "10.0.0.0/16",
            "hub_cidr": "10.0.0.0/20",
            "audit_retention_days": "2555",
            "centralized_logging": "true",
            "cicd_mode": "private",
            "cicd_placement": "SharedServices/BuildVPC",
            "egress_inspection": "required",
            "inspection_pattern": "centralized-nat",
            "inspection_vendor": "aws-network-firewall",
            "hybrid_required": "false",
            "data_residency": "true",
            "encryption_key_management": "aws-kms-hsm",
            "network_segmentation": "true",
        },
        notes={
            "architect": "PCI-DSS scope isolation, SOX audit trails, payment data residency.",
            "engineer": "HSM-backed KMS, dedicated payment VPC, centralized egress inspection.",
        },
        tags=["financial", "pci-dss", "sox", "payment-processing"],
    ),
    CatalogEntry(
        name="lza-healthcare",
        description="Healthcare with HIPAA, PHI encryption, and BAA coverage",
        pattern="healthcare",
        decisions={
            "primary_region": "eu-central-1",
            "topology": "hub-spoke",
            "central_network_account": "Network",
            "network_cidr": "10.0.0.0/16",
            "hub_cidr": "10.0.0.0/20",
            "audit_retention_days": "2555",
            "centralized_logging": "true",
            "cicd_mode": "private",
            "cicd_placement": "SharedServices/BuildVPC",
            "egress_inspection": "required",
            "inspection_pattern": "centralized-nat",
            "inspection_vendor": "aws-network-firewall",
            "hybrid_required": "false",
            "phi_encryption": "true",
            "audit_access_logging": "true",
            "business_associate_agreements": "true",
        },
        notes={
            "architect": "HIPAA compliance, PHI access logging, BAA-covered vendor selection.",
            "engineer": "End-to-end encryption, audit logging, restricted vendor list.",
        },
        tags=["healthcare", "hipaa", "phi", "baa"],
    ),
]

for _entry in _LZA_ENTRIES:
    ConfigCatalog.register_builtin(_entry)
