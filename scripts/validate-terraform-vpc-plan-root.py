"""Validate the exact approved Terraform VPC root without AWS credentials."""

from intent_engine.patterns.terraform_vpc.plan import validate_approved_root

if __name__ == "__main__":
    validate_approved_root()
    print("Terraform VPC approved root: init and validate passed")
