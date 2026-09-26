# Landing-zone policy over the emitted configuration bundle.
#
# Input is the merged bundle: {organization, accounts, global, iam, network, security}.
# These are organization rules about the artifact. Intent-level contradictions are
# caught earlier by the graph review, not here.

package lza

import rego.v1

approved_regions := {
	"eu-central-1",
	"eu-west-1",
	"eu-west-2",
	"eu-north-1",
	"us-east-1",
	"us-west-2",
}

secret_smell := ["password", "secret_key", "aws_access_key_id", "private_key", "BEGIN RSA"]

deny contains msg if {
	input.global.terminationProtection != true
	msg := "global-config: terminationProtection must be enabled"
}

deny contains msg if {
	input.global.logging.cloudtrail.organizationTrail != true
	msg := "global-config: an organization CloudTrail is required"
}

deny contains msg if {
	some region in input.global.enabledRegions
	not region in approved_regions
	msg := sprintf("global-config: region %q is outside the approved region set", [region])
}

home_region_enabled if {
	some region in input.global.enabledRegions
	region == input.global.homeRegion
}

deny contains msg if {
	not home_region_enabled
	msg := sprintf("global-config: home region %q is not enabled", [input.global.homeRegion])
}

deny contains msg if {
	input.security.centralSecurityServices.guardduty.enable != true
	msg := "security-config: GuardDuty must be enabled organization-wide"
}

deny contains msg if {
	input.security.centralSecurityServices.s3PublicAccessBlock.enable != true
	msg := "security-config: S3 public access block must be enabled"
}

deny contains msg if {
	input.security.centralSecurityServices.ebsDefaultVolumeEncryption.enable != true
	msg := "security-config: EBS default volume encryption must be enabled"
}

deny contains msg if {
	input.security.iamPasswordPolicy.minimumPasswordLength < 14
	msg := "security-config: minimum password length must be at least 14"
}

# The log archive account must not double as the security audit account.
deny contains msg if {
	some archive in input.accounts.mandatoryAccounts
	some audit in input.accounts.mandatoryAccounts
	archive.description == "Central log archive"
	audit.description == "Security audit account"
	archive.name == audit.name
	msg := "accounts-config: log archive and audit must be separate accounts"
}

deny contains msg if {
	some account in input.accounts.workloadAccounts
	account.organizationalUnit == "Root"
	msg := sprintf("accounts-config: workload account %q must not sit in Root", [account.name])
}

# Handoff artifacts carry references, never credential material.
deny contains msg if {
	some account in input.accounts.workloadAccounts
	some smell in secret_smell
	contains(lower(account.email), lower(smell))
	msg := sprintf("accounts-config: account %q email looks like credential material", [account.name])
}

deny contains msg if {
	some assignment in input.iam.identityCenter.identityCenterAssignments
	count(assignment.deploymentTargets.accounts) == 0
	msg := sprintf("iam-config: assignment %q targets no account", [assignment.name])
}
