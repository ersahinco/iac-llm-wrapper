# Architect Workshop Notes: Incomplete Landing Zone

The company wants a hub-and-spoke AWS landing zone for regulated workloads. Security wants
centralized logging, private delivery pipelines, and no public S3 exposure. Platform team has not
yet named the central network account in the notes.

## Region

- primary_region: eu-central-1

## Topology

- topology: hub-spoke

## Security

- audit_retention_days: 2555
- centralized_logging: true
- kms_rotation_required: true
- s3_block_public_access: true

## CI/CD

- cicd_mode: private
- cicd_placement: SharedServices/BuildVPC
