# Terraform Design

## State

Remote state uses the shared S3 bucket with a project-specific key prefix for `madmallard-platform`.

Locking uses the provider-supported S3 mechanism rather than deprecated `dynamodb_table` configuration.

## Layout

```text
terraform/
  environments/
    prod/
      main.tf
      variables.tf
      outputs.tf
      versions.tf
      terraform.tfvars.example
  modules/
    <module>/
      main.tf
      variables.tf
      outputs.tf
```

## Rules

- variables only in `variables.tf`;
- outputs only in `outputs.tf`;
- no duplicate declarations;
- no secrets in tfvars/state;
- plans reviewed for replacement and cost;
- production is the only deployed environment during the low-cost MVP;
- modules expose explicit contracts;
- external DNS remains outside Terraform unless intentionally added.
