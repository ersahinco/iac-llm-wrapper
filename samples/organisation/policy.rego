package organisation

# AWS enabled regions must be within the organisation's selected LZA region standard.
# This organisation requires logging and detection unless a scoped exception is recorded.
assessments := [
	{"policy_id": "approved-regions", "status": status, "message": message},
	security_assessment,
]

regions := object.get(input.decisions, "enabled_regions", [])
approved := input.references.lza.enabledRegions
outside := sort({region | some region in regions; not region in approved})

status := "not-assessed" if count(regions) == 0

else := "conflict" if count(outside) > 0

else := "passed"

message := "Enabled regions require a usable client answer." if count(regions) == 0

else := sprintf("Regions outside the organisation standard: %v", [outside]) if count(outside) > 0

else := "All stated enabled regions are within the selected organisation standard."

controls := {"centralized_logging", "security_hub_enabled", "guardduty_enabled"}

security_ready if {
	every control in controls {
		is_boolean(input.decisions[control])
	}
}

disabled := {control | some control in controls; input.decisions[control] == false}

accepted_exception(control) if {
	exception := input.references.lza.securityExceptions[control]
	trim_space(exception.owner) != ""
	trim_space(exception.reason) != ""
}

unexcepted := sort({control | some control in disabled; not accepted_exception(control)})

exception_reasons := sort({sprintf("%s: %s — %s", [control, exception.owner, exception.reason]) |
	some control in disabled
	accepted_exception(control)
	exception := input.references.lza.securityExceptions[control]
})

security_assessment := {"policy_id": "security-controls", "status": "not-assessed", "message": "Logging, Security Hub and GuardDuty require explicit boolean answers."} if not security_ready

else := {"policy_id": "security-controls", "status": "conflict", "message": sprintf("Required security controls are disabled: %v. Recorded exceptions: %v.", [unexcepted, exception_reasons])} if count(unexcepted) > 0

else := {"policy_id": "security-controls", "status": "warning", "message": sprintf("Disabled controls have recorded exceptions: %v.", [exception_reasons])} if count(disabled) > 0

else := {"policy_id": "security-controls", "status": "passed", "message": "All selected security controls are enabled."}
