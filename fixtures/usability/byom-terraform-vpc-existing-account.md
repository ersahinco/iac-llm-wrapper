# Existing Account Workload Trial: Terraform VPC Module

The platform networking team owns an approved Terraform module wrapper around
`terraform-aws-modules/vpc/aws`. The application team is deploying into an
existing AWS account through the owner-controlled networking pipeline.

This handoff should capture module inputs, target account, and pipeline routing
only. Do not generate a Terraform root module, provider, backend, deployment
pipeline, or apply instructions from these notes.

## VPC Module

- vpc_name: reporting-vpc
- primary_region: eu-central-1
- cidr: 10.44.0.0/16
- az_count: 2

## Subnets

- public_subnet_cidrs: 10.44.0.0/24, 10.44.1.0/24
- private_subnet_cidrs: 10.44.10.0/24, 10.44.11.0/24

## Egress

- enable_nat_gateway: true
- single_nat_gateway: false

## DNS

- enable_dns_hostnames: true

## Delivery

- target_account_id: 444455556666
- deployment_pipeline_ref: github://workload-networking/reporting-vpc-deploy

## Review Notes

- Network owner reviews module inputs before the owner pipeline consumes them.
- Checkov evidence should come from the owner Terraform module path, not from
  generated `terraform.tfvars` alone.
