"""Validate the approved Terraform VPC root and initialized module content."""

from intent_engine.patterns.terraform_vpc.plan import validate_approved_root

if __name__ == "__main__":
    validate_approved_root()
    print("Terraform VPC approved root: init, module identity, and validate passed")
