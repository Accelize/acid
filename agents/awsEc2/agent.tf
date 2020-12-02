/*
AWS EC2 Provider
*/
provider "aws" {
  region = var.region
}

variable "instanceType" {
  type        = string
  default     = "t3a.micro"
  description = "Instance type."
}

variable "spot" {
  type        = bool
  default     = true
  description = "Use spot instance."
}

variable "region" {
  type        = string
  default     = "eu-west-1"
  description = "AWS region."
}

data "aws_ami" "agent" {
  most_recent = true
  owners      = [local.image["owner"]]
  filter {
    name   = "name"
    values = [local.image["name"]]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_key_pair" "agent" {
  key_name   = local.name
  public_key = local.public_key
}

resource "aws_security_group" "agent" {
  name = local.name
  dynamic "ingress" {
    for_each = local.firewall_rules
    content {
      from_port   = ingress.value.port
      to_port     = ingress.value.port
      protocol    = ingress.value.protocol
      cidr_blocks = ingress.value.cidr_blocks
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_spot_instance_request" "agent" {
  ami             = data.aws_ami.agent.id
  instance_type   = var.instanceType
  security_groups = [aws_security_group.agent.name]
  key_name        = aws_key_pair.agent.key_name
  tags = {
    Name = local.name
  }
  root_block_device {
    delete_on_termination = true
  }
  count                = var.spot ? 1 : 0
  spot_type            = "one-time"
  wait_for_fulfillment = true
  provisioner "local-exec" {
    # "tags" apply to spot instance request and needs to be applied to instance
    # https://github.com/terraform-providers/terraform-provider-aws/issues/32
    command = <<-EOF
    aws ec2 create-tags --region eu-west-1 \
    --resources ${self.spot_instance_id} --tags Key=Name,Value="${local.name}" \
    EOF
  }

  provisioner "remote-exec" {
    # Wait until instance is ready
    inline = ["cd"]
    connection {
      host        = self.public_ip
      type        = "ssh"
      user        = local.user
      private_key = local.private_key
    }
  }
  provisioner "local-exec" {
    command = "${local.ansible} -i '${self.public_ip},'"
  }
}

resource "aws_instance" "agent" {
  ami             = data.aws_ami.agent.id
  instance_type   = var.instanceType
  security_groups = [aws_security_group.agent.name]
  key_name        = aws_key_pair.agent.key_name
  tags = {
    Name = local.name
  }
  root_block_device {
    delete_on_termination = true
  }
  count                                = var.spot ? 0 : 1
  instance_initiated_shutdown_behavior = "terminate"

  provisioner "remote-exec" {
    # Wait until instance is ready
    inline = ["cd"]
    connection {
      host        = self.public_ip
      type        = "ssh"
      user        = local.user
      private_key = local.private_key
    }
  }
  provisioner "local-exec" {
    command = "${local.ansible} -i '${self.public_ip},'"
  }
}

locals {
  _instances = var.spot ? aws_spot_instance_request.agent : aws_instance.agent
  # IP address, needs to handle the case instance was terminated by timeout
  ip_address    = length(local._instances) > 0 ? lookup(local._instances[0], "public_ip") : null
  user          = local.image["user"]
  image_version = data.aws_ami.agent.name
}
