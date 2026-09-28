# Synthetic workload discussion — initial requests

- vpc_name: discussion-workload
- network_cidr: 10.20.0.0/16
- availability_zones: eu-central-1a, eu-central-1b
- private_subnets: 10.20.1.0/24, 10.20.1.0/25
- routing_domain: corporate
- environment: development
- instance_type: r5.xlarge
- detailed_monitoring: false

These requests deliberately conflict with the selected network and instance policy.
