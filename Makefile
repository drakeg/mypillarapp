ENV ?= prod
TF_DIR := terraform/environments/$(ENV)

.PHONY: tf-fmt tf-init tf-validate tf-plan tf-apply tf-output tf-destroy package

tf-fmt:
	terraform fmt -recursive terraform

tf-init:
	cd $(TF_DIR) && terraform init

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
