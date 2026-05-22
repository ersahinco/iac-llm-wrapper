# Invalid Landing Zone Design

## Topology

- topology: hub-spoke

## Accounts

- PaymentsProd: ou=Workloads/Prod, description=Payments production account

## CI/CD

- mode: private

## Workloads

- payments-api: target_account=PaymentsProd, network_mode=private
