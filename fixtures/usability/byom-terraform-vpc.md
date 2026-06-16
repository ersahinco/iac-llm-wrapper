# BYOM Trial: Terraform VPC Module

The network team already owns a Terraform module based on `terraform-aws-modules/vpc/aws`.
Architects only need to capture decisions. Engineers need exact variables.

## VPC Module

- vpc_name: orders-vpc
- primary_region: eu-central-1
- cidr: 10.30.0.0/16
- az_count: 2

## Subnets

- public_subnet_cidrs: 10.30.0.0/24, 10.30.1.0/24
- private_subnet_cidrs: 10.30.10.0/24, 10.30.11.0/24

## Egress

- enable_nat_gateway: true
- single_nat_gateway: false

## DNS

- enable_dns_hostnames: true

## Delivery

- target_account_id: 111122223333
- deployment_pipeline_ref: github://platform-networking/vpc-deploy
