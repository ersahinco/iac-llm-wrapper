# Synthetic workload discussion — corrected answers

- vpc_name: discussion-workload
- network_cidr: 10.42.0.0/16
- availability_zones: eu-central-1a, eu-central-1b
- private_subnets: 10.42.1.0/24, 10.42.2.0/24
- routing_domain: corporate
- environment: development
- instance_type: m5.large
- detailed_monitoring: false

The selected reference records a synthetic performance-test exception for m5.large.
The exception and disabled-monitoring warning must remain visible in the handoff.
