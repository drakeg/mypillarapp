ENV ?= prod
TF_DIR := terraform/environments/$(ENV)
BACKEND_CONFIG := $(TF_DIR)/backend.hcl
TF_INIT_ARGS := $(if $(wildcard $(BACKEND_CONFIG)),-backend-config=backend.hcl,)

.PHONY: tf-fmt tf-init tf-init-migrate tf-init-reconfigure tf-validate tf-plan tf-apply tf-output tf-destroy package

tf-fmt:
	terraform fmt -recursive terraform

# Standard init. Uses terraform/environments/$(ENV)/backend.hcl when present.
tf-init:
	cd $(TF_DIR) && terraform init $(TF_INIT_ARGS)

# Use this once when moving from local terraform.tfstate to the S3 backend.
tf-init-migrate:
	cd $(TF_DIR) && terraform init $(TF_INIT_ARGS) -migrate-state

# Use this if backend settings change and Terraform asks for reconfiguration.
tf-init-reconfigure:
	cd $(TF_DIR) && terraform init $(TF_INIT_ARGS) -reconfigure

tf-validate:
	cd $(TF_DIR) && terraform validate

tf-plan:
	cd $(TF_DIR) && terraform plan

tf-apply:
	cd $(TF_DIR) && terraform apply

tf-output:
	cd $(TF_DIR) && terraform output

tf-destroy:
	cd $(TF_DIR) && terraform destroy
