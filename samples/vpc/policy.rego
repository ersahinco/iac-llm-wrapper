package organisation

# New VPCs must not overlap allocations in the selected routing domain.
# Instance types follow the environment allowlist; scoped exceptions remain warnings.
# Disabled detailed monitoring is an advisory discussion item.

import rego.v1

assessments := [network_assessment, instance_assessment, monitoring_assessment]

allocations := input.references.estate.routing_domains[input.decisions.routing_domain]

network_ready if {
	net.cidr_is_valid(input.decisions.network_cidr)
	is_array(allocations)
	every allocation in allocations {
		is_string(allocation.name)
		allocation.name != ""
		net.cidr_is_valid(allocation.cidr)
	}
}

overlaps := sort({sprintf("%s (%s)", [allocation.name, allocation.cidr]) |
	some allocation in allocations
	net.cidr_intersects(input.decisions.network_cidr, allocation.cidr)
})

network_assessment := {"policy_id": "existing-networks", "status": "not-assessed", "message": "Supply a valid VPC CIDR and a complete allocation list for the selected routing domain."} if not network_ready

else := {"policy_id": "existing-networks", "status": "conflict", "message": sprintf("VPC %s overlaps %v in routing domain %s.", [input.decisions.network_cidr, overlaps, input.decisions.routing_domain])} if count(overlaps) > 0

else := {"policy_id": "existing-networks", "status": "passed", "message": "No overlap with the supplied routing-domain allocations; owner must confirm snapshot completeness."}

allowed_types := input.references.estate.instance_types[input.decisions.environment]

instance_ready if {
	is_string(input.decisions.instance_type)
	input.decisions.instance_type != ""
	is_array(allowed_types)
	count(allowed_types) > 0
	every kind in allowed_types {
		is_string(kind)
		kind != ""
	}
}

exceptions := sort({sprintf("%s — %s", [exception.owner, exception.reason]) |
	some exception in input.references.estate.instance_exceptions
	exception.environment == input.decisions.environment
	exception.instance_type == input.decisions.instance_type
	is_string(exception.owner)
	is_string(exception.reason)
	trim_space(exception.owner) != ""
	trim_space(exception.reason) != ""
})

instance_assessment := {"policy_id": "instance-size", "status": "not-assessed", "message": "Supply an instance type and a nonempty environment allowlist."} if not instance_ready

else := {"policy_id": "instance-size", "status": "passed", "message": "Instance type is in the environment allowlist; capacity still needs owner validation."} if input.decisions.instance_type in allowed_types

else := {"policy_id": "instance-size", "status": "warning", "message": sprintf("Out-of-scope instance type %s: recorded exception %v. Standard alternatives: %v.", [input.decisions.instance_type, exceptions, allowed_types])} if count(exceptions) > 0

else := {"policy_id": "instance-size", "status": "conflict", "message": sprintf("Instance type %s is outside %s scope. Allowed alternatives: %v.", [input.decisions.instance_type, input.decisions.environment, allowed_types])}

monitoring_assessment := {"policy_id": "monitoring", "status": "passed", "message": "Detailed monitoring is requested."} if input.decisions.detailed_monitoring == true

else := {"policy_id": "monitoring", "status": "warning", "message": "Detailed monitoring is disabled. Discuss detection needs and cost with the workload owner."} if input.decisions.detailed_monitoring == false

else := {"policy_id": "monitoring", "status": "not-assessed", "message": "Detailed monitoring needs an explicit boolean answer."}
