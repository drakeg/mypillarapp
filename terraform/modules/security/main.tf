variable "project_name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "ssh_cidr" {
  type    = string
  default = ""
}

variable "enable_ssh" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_security_group" "web" {
  name        = "${var.project_name}-web"
  description = "Mad Mallard Platform web instance security group"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = var.enable_ssh && var.ssh_cidr != "" ? [var.ssh_cidr] : []
    content {
      description = "SSH restricted"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-web-sg"
  })
}

output "web_security_group_id" {
  value = aws_security_group.web.id
}
