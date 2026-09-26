# Illustrative VPC discussion

The existing enterprise network uses on-premises routing and SD-WAN.
The planned AWS landing zone must connect to the existing enterprise network.
Existing Entra ID will provide workforce identity to planned AWS IAM Identity Center.
The planned VPC is named banking-app.
The approved VPC address range is 10.42.0.0/16.
The approved availability zones are eu-central-1a and eu-central-1b.
Private subnet address ranges have not been decided.

This is a synthetic example. Network connectivity and identity federation are
discussion context; this VPC input contract does not configure those integrations.
