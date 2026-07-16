variable "region" {
  description = "AWS region for the approved VPC module."
  type        = string
}

variable "name" {
  description = "VPC name."
  type        = string
}

variable "cidr" {
  description = "Primary VPC IPv4 CIDR."
  type        = string
}

variable "azs" {
  description = "Availability zones used by the VPC."
  type        = list(string)
}

variable "public_subnets" {
  description = "Public subnet IPv4 CIDRs."
  type        = list(string)
}

variable "private_subnets" {
  description = "Private subnet IPv4 CIDRs."
  type        = list(string)
}

variable "enable_nat_gateway" {
  description = "Whether the VPC module creates NAT gateways."
  type        = bool
}

variable "single_nat_gateway" {
  description = "Whether the VPC module shares one NAT gateway across availability zones."
  type        = bool
}

variable "enable_dns_hostnames" {
  description = "Whether DNS hostnames are enabled in the VPC."
  type        = bool
}
