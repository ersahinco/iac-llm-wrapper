# CloudFormation Parameter Handoff Evaluation

The application team owns an approved CloudFormation template for the orders
service. The handoff should capture only the stack parameters and review
context for the existing pipeline. It must not generate a template or deploy.

## CloudFormation

- stack_name: orders-service-prod
- template_url: s3://approved-templates/orders-service.yaml
- region: eu-central-1

## Parameters

- parameter_overrides: Environment=prod, ServiceName=orders, DesiredCount=3

## Execution

- capabilities: CAPABILITY_NAMED_IAM
- execution_role_arn: arn:aws:iam::123456789012:role/cfn-execution-orders
