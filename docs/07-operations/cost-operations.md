# Cost Operations

## Cost Principles

- Prefer Standard SSM parameters over Secrets Manager when requirements permit.
- Use one small EC2 instance during MVP.
- Avoid RDS until availability, concurrency, or durability requires it.
- Avoid Route 53 when external DNS is already available.
- Avoid Elastic IP until stable addressing justifies its cost.
- Use SES for low-cost transactional email.
- Add CloudWatch retention and alarms selectively.
- Review cost before introducing every AWS service.

## Monthly Review

Review EC2, EBS, S3, SES, data transfer, CloudWatch, and unexpected service usage.
