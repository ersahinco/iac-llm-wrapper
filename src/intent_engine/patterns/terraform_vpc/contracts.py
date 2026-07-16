"""Target contract and policy mappings for Terraform VPC handoff."""

from intent_engine.core.contracts import ArtifactContract, DecisionLineage, TargetContract
from intent_engine.core.policy import (
    PolicyCheckRef,
    PolicyControl,
    PolicyPack,
    PolicyRequirementMapping,
)

CONTRACT = TargetContract(
    name="terraform-aws-vpc-module",
    kind="terraform-module",
    source_url="https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws",
    required_decisions=[
        "vpc_name",
        "cidr",
        "public_subnet_cidrs",
        "private_subnet_cidrs",
        "target_account_id",
        "deployment_pipeline_ref",
    ],
    artifacts=[
        ArtifactContract(
            name="decision-report.yaml",
            required_paths=[
                "vpc.name",
                "vpc.region",
                "vpc.cidr",
                "vpc.publicSubnetCidrs[]",
                "vpc.privateSubnetCidrs[]",
                "delivery.targetAccountId",
                "delivery.deploymentPipelineRef",
            ],
        ),
        ArtifactContract(
            name="module-inputs.yaml",
            required_paths=[
                "moduleInputs[]",
                "moduleInputs[].moduleName",
                "moduleInputs[].variables.name",
                "moduleInputs[].variables.cidr",
                "moduleInputs[].variables.public_subnets[]",
                "moduleInputs[].variables.private_subnets[]",
            ],
        ),
        ArtifactContract(
            name="terraform.tfvars",
            required=False,
            description="Reference Terraform variable file generated from module inputs.",
        ),
    ],
    lineage=[
        DecisionLineage(
            decision="vpc_name",
            artifact="decision-report.yaml",
            path="vpc.name",
        ),
        DecisionLineage(
            decision="cidr",
            artifact="decision-report.yaml",
            path="vpc.cidr",
        ),
        DecisionLineage(
            decision="public_subnet_cidrs",
            artifact="decision-report.yaml",
            path="vpc.publicSubnetCidrs",
        ),
        DecisionLineage(
            decision="private_subnet_cidrs",
            artifact="decision-report.yaml",
            path="vpc.privateSubnetCidrs",
        ),
        DecisionLineage(
            decision="target_account_id",
            artifact="decision-report.yaml",
            path="delivery.targetAccountId",
        ),
        DecisionLineage(
            decision="deployment_pipeline_ref",
            artifact="decision-report.yaml",
            path="delivery.deploymentPipelineRef",
        ),
    ],
)

POLICY_PACK = PolicyPack(
    name="regulated-vpc-baseline-v1",
    version="1.0.0",
    description=(
        "Baseline regulated-environment policy mappings for existing-account Terraform "
        "AWS VPC module handoff."
    ),
    frameworks=["SOC2", "PCI", "HIPAA", "NIST", "CUSTOM_CLIENT"],
    controls=[
        PolicyControl(
            id="VPC-DELIVERY-001",
            title="Owner-controlled account and pipeline routing is declared",
            description=(
                "The handoff must identify the existing target account and the owner "
                "pipeline that consumes reviewed module inputs."
            ),
            frameworks=["SOC2", "NIST", "CUSTOM_CLIENT"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["target_account_id", "deployment_pipeline_ref"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:delivery.targetAccountId",
                    "decision-report.yaml:delivery.deploymentPipelineRef",
                ],
                owner_policy_refs=["owner://pipeline-routing-required"],
            ),
        ),
        PolicyControl(
            id="VPC-NETWORK-001",
            title="VPC and subnet CIDR plan is explicit",
            description=(
                "Network ranges must be reviewable before the owner pipeline deploys "
                "the approved Terraform module."
            ),
            frameworks=["SOC2", "PCI", "HIPAA", "NIST"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["cidr", "public_subnet_cidrs", "private_subnet_cidrs"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:vpc.cidr",
                    "decision-report.yaml:vpc.publicSubnetCidrs",
                    "decision-report.yaml:vpc.privateSubnetCidrs",
                    "module-inputs.yaml:moduleInputs[].variables.cidr",
                    "module-inputs.yaml:moduleInputs[].variables.public_subnets",
                    "module-inputs.yaml:moduleInputs[].variables.private_subnets",
                ],
                module_variables=["cidr", "public_subnets", "private_subnets"],
                checkov_check_ids=["CKV_CUSTOM_VPC_001"],
                owner_policy_refs=["owner://network-cidr-allocation"],
            ),
            checks=[
                PolicyCheckRef(
                    check_id="CKV_CUSTOM_VPC_001",
                    name="Client VPC CIDR and subnet allocation policy",
                    source="owner-custom",
                    description=(
                        "Owner-provided Checkov custom policy for approved VPC and subnet ranges."
                    ),
                )
            ],
        ),
        PolicyControl(
            id="VPC-EGRESS-001",
            title="NAT mode is intentional and reviewable",
            frameworks=["PCI", "HIPAA", "NIST"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["enable_nat_gateway", "single_nat_gateway"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:vpc.enableNatGateway",
                    "decision-report.yaml:vpc.singleNatGateway",
                    "module-inputs.yaml:moduleInputs[].variables.enable_nat_gateway",
                    "module-inputs.yaml:moduleInputs[].variables.single_nat_gateway",
                ],
                module_variables=["enable_nat_gateway", "single_nat_gateway"],
                owner_policy_refs=["owner://egress-architecture-review"],
            ),
        ),
        PolicyControl(
            id="VPC-DNS-001",
            title="DNS hostname behavior is declared",
            frameworks=["SOC2", "HIPAA", "NIST"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["enable_dns_hostnames"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:vpc.enableDnsHostnames",
                    "module-inputs.yaml:moduleInputs[].variables.enable_dns_hostnames",
                ],
                module_variables=["enable_dns_hostnames"],
                owner_policy_refs=["owner://dns-platform-baseline"],
            ),
        ),
        PolicyControl(
            id="VPC-ATTACHMENT-001",
            title="Cross-resource VPC attachment checks remain owner-policy references",
            description=(
                "Cross-resource checks such as security-group-to-VPC attachment are "
                "represented as policy references unless the pattern owns the resource "
                "relationship model."
            ),
            frameworks=["PCI", "HIPAA", "NIST", "CUSTOM_CLIENT"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["vpc_name", "cidr"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=["decision-report.yaml:vpc.name", "decision-report.yaml:vpc.cidr"],
                module_variables=["name", "cidr"],
                checkov_check_ids=["CKV_CUSTOM_VPC_ATTACHMENT_001"],
                owner_policy_refs=["owner://vpc-attachment-cross-resource-check"],
            ),
            checks=[
                PolicyCheckRef(
                    check_id="CKV_CUSTOM_VPC_ATTACHMENT_001",
                    name="Client VPC attachment cross-resource policy",
                    source="owner-custom",
                    description=(
                        "Owner-provided custom Checkov policy for relationships such as "
                        "security group attachment to the intended VPC."
                    ),
                )
            ],
        ),
    ],
)
