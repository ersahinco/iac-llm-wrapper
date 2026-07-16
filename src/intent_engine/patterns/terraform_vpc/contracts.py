"""Target contract and policy mappings for Terraform VPC handoff."""

from intent_engine.core.contracts import (
    ArtifactContract,
    ArtifactValueAssertion,
    DecisionLineage,
    TargetContract,
)
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
                "targetModule.source",
                "targetModule.version",
                "targetModule.provider.source",
                "targetModule.provider.version",
            ],
            value_assertions=[
                ArtifactValueAssertion(
                    path="targetModule.source",
                    equals="terraform-aws-modules/vpc/aws",
                ),
                ArtifactValueAssertion(path="targetModule.version", equals="6.6.1"),
                ArtifactValueAssertion(path="targetModule.provider.source", equals="hashicorp/aws"),
                ArtifactValueAssertion(path="targetModule.provider.version", equals="6.53.0"),
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
            name="requirement-graph.json",
            required_paths=[
                "pattern",
                "nodeCount",
                "nodes[]",
                "nodes[].key",
                "nodes[].status",
                "edges",
            ],
            value_assertions=[
                ArtifactValueAssertion(path="pattern", equals="terraform-vpc"),
                ArtifactValueAssertion(path="nodeCount", equals=11),
            ],
        ),
        ArtifactContract(
            name="terraform.tfvars",
            required=False,
            description="Reference Terraform variable file generated from module inputs.",
        ),
        ArtifactContract(
            name="plan-manifest.yaml",
            required_paths=[
                "schemaVersion",
                "target.module.source",
                "target.module.version",
                "target.provider.source",
                "target.provider.version",
                "toolchain.terraformVersion",
                "toolchain.wrapperVersion",
                "approvedRoot.files[]",
                "approvedRoot.files[].name",
                "approvedRoot.files[].sha256",
                "approvedRoot.sha256",
                "approvedModule.releaseCommit",
                "approvedModule.treeSha256",
                "sourceDocument.mode",
                "sourceDocument.sha256",
                "maturity.configReady.status",
                "maturity.planReady.status",
                "maturity.planReady.planAllowed",
                "maturity.planProven.status",
                "maturity.planProven.proven",
            ],
            value_assertions=[
                ArtifactValueAssertion(
                    path="schemaVersion",
                    equals="intent-engine/plan-manifest/v1",
                ),
                ArtifactValueAssertion(
                    path="target.module.source",
                    equals="terraform-aws-modules/vpc/aws",
                ),
                ArtifactValueAssertion(path="target.module.version", equals="6.6.1"),
                ArtifactValueAssertion(path="target.provider.source", equals="hashicorp/aws"),
                ArtifactValueAssertion(path="target.provider.version", equals="6.53.0"),
                ArtifactValueAssertion(path="toolchain.terraformVersion", equals="1.15.8"),
                ArtifactValueAssertion(
                    path="approvedModule.releaseCommit",
                    equals="3ffbd46fb1c7733e1b34d8666893280454e27436",
                ),
                ArtifactValueAssertion(
                    path="approvedModule.treeSha256",
                    equals="38386a5d1a9e99cc1fdf8273a70b25b6f9dddca836545a960159d019d193c807",
                ),
                ArtifactValueAssertion(path="maturity.planProven.proven", equals=False),
            ],
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

ATMOS_CONTRACT = TargetContract(
    name="terraform-vpc-atmos-handoff",
    kind="atmos-terraform-component",
    source_url="https://atmos.tools/components/terraform/stack-config",
    required_decisions=[
        "vpc_name",
        "primary_region",
        "cidr",
        "az_count",
        "public_subnet_cidrs",
        "private_subnet_cidrs",
        "enable_nat_gateway",
        "single_nat_gateway",
        "enable_dns_hostnames",
    ],
    artifacts=[
        ArtifactContract(
            name="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            required_paths=[
                "components.terraform.terraform-vpc/intent-defaults.metadata.type",
                "components.terraform.terraform-vpc/intent-defaults.metadata.component",
                "components.terraform.terraform-vpc/intent-defaults.vars.region",
                "components.terraform.terraform-vpc/intent-defaults.vars.name",
                "components.terraform.terraform-vpc/intent-defaults.vars.cidr",
                "components.terraform.terraform-vpc/intent-defaults.vars.azs[]",
                "components.terraform.terraform-vpc/intent-defaults.vars.public_subnets[]",
                "components.terraform.terraform-vpc/intent-defaults.vars.private_subnets[]",
                "components.terraform.terraform-vpc/intent-defaults.vars.enable_nat_gateway",
                "components.terraform.terraform-vpc/intent-defaults.vars.single_nat_gateway",
                "components.terraform.terraform-vpc/intent-defaults.vars.enable_dns_hostnames",
            ],
            value_assertions=[
                ArtifactValueAssertion(
                    path="components.terraform.terraform-vpc/intent-defaults.metadata.type",
                    equals="abstract",
                ),
                ArtifactValueAssertion(
                    path="components.terraform.terraform-vpc/intent-defaults.metadata.component",
                    equals="terraform-vpc",
                ),
            ],
        ),
        ArtifactContract(name="atmos/components/terraform/terraform-vpc/main.tf"),
        ArtifactContract(name="atmos/components/terraform/terraform-vpc/variables.tf"),
        ArtifactContract(name="atmos/components/terraform/terraform-vpc/.terraform.lock.hcl"),
    ],
    lineage=[
        DecisionLineage(
            decision="vpc_name",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.name",
        ),
        DecisionLineage(
            decision="primary_region",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.region",
        ),
        DecisionLineage(
            decision="cidr",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.cidr",
        ),
        DecisionLineage(
            decision="az_count",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.azs",
        ),
        DecisionLineage(
            decision="public_subnet_cidrs",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.public_subnets",
        ),
        DecisionLineage(
            decision="private_subnet_cidrs",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.private_subnets",
        ),
        DecisionLineage(
            decision="enable_nat_gateway",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.enable_nat_gateway",
        ),
        DecisionLineage(
            decision="single_nat_gateway",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.single_nat_gateway",
        ),
        DecisionLineage(
            decision="enable_dns_hostnames",
            artifact="atmos/stacks/catalog/terraform-vpc-intent.yaml",
            path="components.terraform.terraform-vpc/intent-defaults.vars.enable_dns_hostnames",
        ),
    ],
)

PLAN_EVIDENCE_CONTRACT = TargetContract(
    name="terraform-vpc-plan-evidence",
    kind="terraform-speculative-plan-evidence",
    source_url="intent-engine://contracts/terraform-vpc-plan-evidence/v2",
    required_decisions=["terraformPlanEvidence"],
    artifacts=[
        ArtifactContract(
            name="terraform-plan-evidence.yaml",
            required_paths=[
                "schemaVersion",
                "timestamp",
                "status",
                "pattern",
                "bundle.replayManifestSha256",
                "bundle.bundleDigest",
                "bundle.sourceSha256",
                "target.moduleSource",
                "target.moduleVersion",
                "target.moduleReleaseCommit",
                "target.moduleTreeSha256",
                "target.providerSource",
                "target.providerVersion",
                "toolchain.terraformVersion",
                "toolchain.wrapperVersion",
                "toolchain.approvedRootSha256",
                "plan.executionStatus",
                "plan.formatVersion",
                "plan.terraformVersion",
                "plan.applyable",
                "plan.complete",
                "plan.errored",
                "plan.binaryPlanSha256",
                "plan.planJsonSha256",
                "plan.moduleContentVerified",
                "stages[]",
                "stages[].name",
                "stages[].status",
                "resourceChanges",
                "changeSummary.create",
                "changeSummary.update",
                "changeSummary.delete",
                "changeSummary.replace",
                "changeSummary.noOp",
                "blockers",
                "conformance.status",
                "conformance.requirementSetId",
                "conformance.specification.id",
                "conformance.specification.sha256",
                "conformance.identities.requirementGraphSha256",
                "conformance.identities.decisionAuditSha256",
                "conformance.identities.policyGraphSha256",
                "conformance.identities.planManifestSha256",
                "conformance.identities.decisionReportSha256",
                "conformance.identities.moduleInputsSha256",
                "conformance.identities.targetContractSha256",
                "conformance.identities.policyPackSha256",
                "conformance.requirements[]",
                "conformance.requirements[].requirementId",
                "conformance.requirements[].graphKey",
                "conformance.requirements[].outcome",
                "conformance.requirements[].proofClass",
                "conformance.controls[]",
                "conformance.controls[].controlId",
                "conformance.controls[].outcome",
                "conformance.controls[].proofClass",
                "conformance.notApplicableRequirementIds",
                "conformance.deferredGates",
                "conformance.resources",
                "conformance.ownerReviewRequired",
                "guidance[]",
                "ownerReviewRequired",
                "applyAllowed",
                "boundary",
            ],
            value_assertions=[
                ArtifactValueAssertion(
                    path="schemaVersion",
                    equals="intent-engine/terraform-plan-evidence/v2",
                ),
                ArtifactValueAssertion(path="pattern", equals="terraform-vpc"),
                ArtifactValueAssertion(path="target.moduleVersion", equals="6.6.1"),
                ArtifactValueAssertion(path="target.providerVersion", equals="6.53.0"),
                ArtifactValueAssertion(path="toolchain.terraformVersion", equals="1.15.8"),
                ArtifactValueAssertion(
                    path="target.moduleReleaseCommit",
                    equals="3ffbd46fb1c7733e1b34d8666893280454e27436",
                ),
                ArtifactValueAssertion(
                    path="target.moduleTreeSha256",
                    equals="38386a5d1a9e99cc1fdf8273a70b25b6f9dddca836545a960159d019d193c807",
                ),
                ArtifactValueAssertion(
                    path="conformance.requirementSetId",
                    equals="terraform-vpc/requirements/v1",
                ),
                ArtifactValueAssertion(
                    path="conformance.specification.id",
                    equals="terraform-vpc/plan-conformance/v2",
                ),
                ArtifactValueAssertion(path="ownerReviewRequired", equals=True),
                ArtifactValueAssertion(path="conformance.ownerReviewRequired", equals=True),
                ArtifactValueAssertion(path="applyAllowed", equals=False),
            ],
        )
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
