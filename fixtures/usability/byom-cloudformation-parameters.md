# BYOM CloudFormation Parameter Trial

Engineer owns an approved CloudFormation template for an app service. The wrapper should capture
only stack parameters and handoff context. It must not generate a CloudFormation template or deploy.

## CloudFormation

- stack_name: orders-service-prod
- template_url: s3://approved-templates/orders-service.yaml
- region: eu-central-1

## Parameters

- parameter_overrides: Environment=prod, ServiceName=orders, DesiredCount=3

## Execution

- capabilities: CAPABILITY_NAMED_IAM
- execution_role_arn: arn:aws:iam::123456789012:role/cfn-execution-orders
