# Project Name — Landing Zone Design

> Fill in each section with your requirements. Use `key: value` format for
> structured fields and prose for context. Remove sections that don't apply.
> The LLM will extract decisions from your descriptions.
>
> Generate this template: `intent-engine template --pattern baseline -o design.md`

## Region

- primary: <!-- e.g. eu-central-1, us-east-1 -->

## Topology

- topology: <!-- hub-spoke or single-vpc -->

## Organizational Units

<!-- Each line: OU Name: Description -->
<!-- e.g. - Security: Security baseline OU -->

-

## Accounts

<!-- Each line: AccountName: ou=OU_Name, description=Description -->
<!-- The OU referenced must match one of the Organizational Units above -->
<!-- e.g. - Network: ou=Infrastructure, description=Central networking account -->

-

## Network

- cidr: <!-- e.g. 10.0.0.0/16 -->
- hub_cidr: <!-- e.g. 10.0.0.0/20 (hub-spoke only) -->
- central_network_account: <!-- hub-spoke only -->

## Security

- audit_retention_days: <!-- e.g. 2555 -->
- centralized_logging: <!-- true or false -->
- kms_rotation: <!-- true or false -->

## CI/CD

- mode: <!-- private or public -->
- placement: <!-- VPC name or subnet (private mode only) -->
- runner_platform: <!-- enterprise or self-hosted -->

## Workloads

<!-- Each line: name: target_account=..., network_mode=..., port=..., cpu=..., memory=... -->
<!-- e.g. - api-service: target_account=Prod, network_mode=private, port=8080, cpu=512, memory=1024 -->

-

## Hybrid Connectivity (optional)

- hybrid_required: <!-- true or false -->
- dns_model: <!-- aws-resolver, shared-services, route53-resolver -->
- on_prem_cidrs: <!-- comma-separated CIDRs -->

## Egress Inspection (optional)

- egress_inspection: <!-- required or none -->
- inspection_vendor: <!-- aws-network-firewall, paloalto, checkpoint, fortinet -->
