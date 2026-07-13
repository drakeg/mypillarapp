# AWS Cost Model

## Current cost strategy

- one small EC2 instance;
- EBS root/data storage;
- Standard SSM parameters;
- S3 state/artifacts;
- SES pay-per-use;
- external DNS;
- no RDS;
- no NAT Gateway;
- no load balancer;
- no Elastic IP unless later enabled.

## Review checklist for a new service

1. What requirement does it satisfy?
2. What is the monthly fixed cost?
3. What is the usage-based cost?
4. Is there a free or already-running alternative?
5. Can it be disabled when unused?
6. What migration path exists if postponed?
7. What alarms/budgets prevent surprises?

## Scale decision

RDS becomes appropriate when customer commitments, concurrent writes, backup guarantees, or multi-instance application deployment exceed SQLite's safe operating envelope.
