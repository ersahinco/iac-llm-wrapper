# Landing-zone policy over the emitted configuration bundle.
#
# Input is the merged bundle: {organization, accounts, global, iam, network, security}.
# General artifact advice. Organisation restrictions and exceptions are assessed
# from the selected policy snapshot during review and export.

package lza

import rego.v1

secret_smell := ["password", "secret_key", "aws_access_key_id", "private_key", "BEGIN RSA"]

deny contains msg if {
	not input.global.terminationProtection == true
	msg := "global-config: terminationProtection must be enabled"
}

deny contains msg if {
	not input.global.logging.cloudtrail.organizationTrail == true
	msg := "global-config: an organization CloudTrail is required"
}

home_region_enabled if input.global.homeRegion in input.global.enabledRegions

deny contains msg if {
	not home_region_enabled
	msg := "global-config: homeRegion must be present in enabledRegions"
}

deny contains msg if {
	not input.security.centralSecurityServices.guardduty.enable == true
	msg := "security-config: GuardDuty must be enabled organization-wide"
}

deny contains msg if {
	not input.security.centralSecurityServices.securityHub.enable == true
	msg := "security-config: consider enabling Security Hub organization-wide"
}

deny contains msg if {
	not input.security.centralSecurityServices.s3PublicAccessBlock.enable == true
	msg := "security-config: S3 public access block must be enabled"
}

deny contains msg if {
	not input.security.centralSecurityServices.ebsDefaultVolumeEncryption.enable == true
	msg := "security-config: EBS default volume encryption must be enabled"
}

password_length_valid if {
	is_number(input.security.iamPasswordPolicy.minimumPasswordLength)
	input.security.iamPasswordPolicy.minimumPasswordLength >= 14
}

deny contains msg if {
	not password_length_valid
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
	not assignment_targets_valid(assignment)
	msg := "iam-config: every assignment must target a nonempty array of account names"
}

# Preconditions for the rules above, not a substitute for the LZA schema.
required_fields := [
	[["organization"], "object"],
	[["network"], "object"],
	[["global", "homeRegion"], "string"],
	[["global", "enabledRegions"], "array"],
	[["accounts", "mandatoryAccounts"], "array"],
	[["accounts", "workloadAccounts"], "array"],
	[["iam", "identityCenter", "identityCenterAssignments"], "array"],
]

deny contains msg if {
	some field in required_fields
	type_name(object.get(input, field[0], null)) != field[1]
	msg := sprintf("%s: required %s is missing or has the wrong type", [concat(".", field[0]), field[1]])
}

deny contains msg if {
	some region in input.global.enabledRegions
	not is_string(region)
	msg := "global-config: enabledRegions must contain region names"
}

deny contains msg if {
	some kind in ["mandatoryAccounts", "workloadAccounts"]
	some account in input.accounts[kind]
	some field in ["name", "description", "email", "organizationalUnit"]
	not nonempty_string(object.get(account, field, null))
	msg := sprintf("accounts-config: every %s entry needs a nonempty %s", [kind, field])
}

deny contains msg if {
	some kind in ["mandatoryAccounts", "workloadAccounts"]
	some account in input.accounts[kind]
	not is_object(account)
	msg := sprintf("accounts-config: %s entries must be objects", [kind])
}

deny contains msg if {
	count(input.accounts.mandatoryAccounts) == 0
	msg := "accounts-config: mandatoryAccounts must not be empty"
}

nonempty_string(value) if {
	is_string(value)
	count(trim_space(value)) > 0
}

assignment_targets_valid(assignment) if {
	is_array(assignment.deploymentTargets.accounts)
	count(assignment.deploymentTargets.accounts) > 0
	every account in assignment.deploymentTargets.accounts {
		nonempty_string(account)
	}
}
