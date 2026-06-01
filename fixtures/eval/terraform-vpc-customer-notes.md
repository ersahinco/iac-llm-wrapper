# Terraform VPC Customer Notes

The networking squad owns an approved `terraform-aws-modules/vpc/aws` module
wrapper. This handoff should capture module inputs only. Do not generate a root
Terraform stack, provider block, backend, pipeline, or deployment instructions
from these notes.

## Meeting Summary

The payments platform is moving to a fresh VPC for the merchant settlement
service. The team wants three availability zones, per-AZ NAT for resilience, and
DNS hostnames enabled because private service discovery depends on them.

## VPC Module

- vpc_name: payments-shared-vpc
- primary_region: eu-west-1
- cidr: 10.90.0.0/16
- az_count: 3

## Subnets

The subnet plan was copied from IPAM approval NW-4127.

- public_subnet_cidrs: 10.90.0.0/24, 10.90.1.0/24, 10.90.2.0/24
- private_subnet_cidrs: 10.90.10.0/24, 10.90.11.0/24, 10.90.12.0/24

## Egress

Finance operations rejected a single shared NAT gateway for production.

- enable_nat_gateway: true
- single_nat_gateway: false

## DNS

- enable_dns_hostnames: true

## Review Notes

- Platform networking reviews `module-inputs.yaml`.
- Application platform reviews the generated `terraform.tfvars` as a reference
  input file only.
- Existing Terraform automation owns planning and applying.
