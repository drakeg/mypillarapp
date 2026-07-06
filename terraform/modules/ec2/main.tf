variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "security_group_ids" {
  type = list(string)
}

variable "instance_profile_name" {
  type = string
}

variable "public_key" {
  type    = string
  default = ""
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "ami_family" {
  type    = string
  default = "amazon-linux-2023"
}

variable "ami_id" {
  type    = string
  default = ""
}

variable "root_volume_size" {
  type    = number
  default = 20
}

variable "primary_domain" {
  type = string
}

variable "additional_domains" {
  type    = list(string)
  default = []
}

variable "acme_email" {
  type = string
}

variable "security_profile" {
  type    = string
  default = "standard"
}

variable "use_elastic_ip" {
  type    = bool
  default = false
}

variable "user_data_replace_on_change" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  domain_list = concat([var.primary_domain], var.additional_domains)
  caddy_sites = join("\n\n", [for d in local.domain_list : <<-SITE
${d} {
    encode zstd gzip
    reverse_proxy host.docker.internal:8000
}
SITE
  ])
  ssh_user = var.ami_family == "amazon-linux-2023" ? "ec2-user" : "ubuntu"
}

data "aws_ami" "al2023" {
  count       = var.ami_id == "" && var.ami_family == "amazon-linux-2023" ? 1 : 0
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_ami" "ubuntu_2404" {
  count       = var.ami_id == "" && var.ami_family == "ubuntu-24.04" ? 1 : 0
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

data "aws_ami" "ubuntu_2204" {
  count       = var.ami_id == "" && var.ami_family == "ubuntu-22.04" ? 1 : 0
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

locals {
  selected_ami_id = var.ami_id != "" ? var.ami_id : (
    var.ami_family == "amazon-linux-2023" ? data.aws_ami.al2023[0].id : (
      var.ami_family == "ubuntu-24.04" ? data.aws_ami.ubuntu_2404[0].id : data.aws_ami.ubuntu_2204[0].id
    )
  )
}

resource "aws_key_pair" "this" {
  count      = var.public_key == "" ? 0 : 1
  key_name   = "${var.project_name}-${var.environment}"
  public_key = var.public_key

  tags = var.tags
}

resource "aws_instance" "this" {
  ami                         = local.selected_ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = var.security_group_ids
  iam_instance_profile        = var.instance_profile_name
  key_name                    = var.public_key == "" ? null : aws_key_pair.this[0].key_name
  associate_public_ip_address = true
  user_data_replace_on_change = var.user_data_replace_on_change

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    primary_domain   = var.primary_domain
    caddy_sites      = local.caddy_sites
    acme_email       = var.acme_email
    security_profile = var.security_profile
  })

  tags = merge(var.tags, {
    Name                = "${var.project_name}-${var.environment}"
    MadMallardPlatform  = "true"
    MadMallardComponent = "web"
  })
}

resource "aws_eip" "this" {
  count  = var.use_elastic_ip ? 1 : 0
  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-web-eip"
  })
}

resource "aws_eip_association" "this" {
  count         = var.use_elastic_ip ? 1 : 0
  instance_id   = aws_instance.this.id
  allocation_id = aws_eip.this[0].id
}

output "public_ip" {
  value = var.use_elastic_ip ? aws_eip.this[0].public_ip : aws_instance.this.public_ip
}

output "instance_public_ip" {
  value = aws_instance.this.public_ip
}

output "elastic_ip" {
  value = var.use_elastic_ip ? aws_eip.this[0].public_ip : ""
}

output "instance_id" {
  value = aws_instance.this.id
}

output "public_dns" {
  value = aws_instance.this.public_dns
}

output "ami_id" {
  value = local.selected_ami_id
}

output "ssh_user" {
  value = local.ssh_user
}
