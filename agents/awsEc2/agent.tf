provider "aws" {
  region = "eu-west-1"
}

variable "instance_type" {
  type        = string
  default     = "f1.2xlarge"
  description = "Instance type to use."
}

variable "spot" {
  type        = bool
  default     = true
  description = "Use spot instance."
}

# Configure AMI
locals {
  # Available images
  ami_users = {
    "amzn_1"                       = "ec2-user"
    "amzn_2"                       = "ec2-user"
    "centos_7"                     = "centos"
    "centos_7_aws_fpga_dev"        = "centos"
    "centos_7_aws_fpga_dev_2017_4" = "centos"
    "centos_7_aws_fpga_dev_2018_2" = "centos"
    "centos_7_aws_fpga_dev_2018_3" = "centos"
    "centos_7_aws_fpga_dev_2019_1" = "centos"
    "centos_7_aws_fpga_dev_2019_2" = "centos"
    "centos_8"                     = "centos"
    "debian_9"                     = "admin"
    "debian_10"                    = "admin"
    "fedora_31"                    = "fedora"
    "fedora_32"                    = "fedora"
    "ubuntu_16_04"                 = "ubuntu"
    "ubuntu_18_04"                 = "ubuntu"
    "ubuntu_20_04"                 = "ubuntu"
  }
  ami_owners = {
    "amzn_1"                       = "amazon"
    "amzn_2"                       = "amazon"
    "centos_7"                     = "125523088429"
    "centos_7_aws_fpga_dev"        = "679593333241"
    "centos_7_aws_fpga_dev_2017_4" = "679593333241"
    "centos_7_aws_fpga_dev_2018_2" = "679593333241"
    "centos_7_aws_fpga_dev_2018_3" = "679593333241"
    "centos_7_aws_fpga_dev_2019_1" = "679593333241"
    "centos_7_aws_fpga_dev_2019_2" = "679593333241"
    "centos_8"                     = "125523088429"
    "debian_9"                     = "379101102735"
    "debian_10"                    = "136693071363"
    "fedora_31"                    = "125523088429"
    "fedora_32"                    = "125523088429"
    "ubuntu_16_04"                 = "099720109477"
    "ubuntu_18_04"                 = "099720109477"
    "ubuntu_20_04"                 = "099720109477"
  }
  ami_names = {
    "amzn_1"                       = "amzn-ami-hvm-*-x86_64-gp2"
    "amzn_2"                       = "amzn2-ami-hvm-*-x86_64-gp2"
    "centos_7"                     = "CentOS 7.* x86_64"
    "centos_7_aws_fpga_dev"        = "FPGA Developer AMI - *"
    "centos_7_aws_fpga_dev_2017_4" = "FPGA Developer AMI - 1.4.*"
    "centos_7_aws_fpga_dev_2018_2" = "FPGA Developer AMI - 1.5.*"
    "centos_7_aws_fpga_dev_2018_3" = "FPGA Developer AMI - 1.6.*"
    "centos_7_aws_fpga_dev_2019_1" = "FPGA Developer AMI - 1.7.*"
    "centos_7_aws_fpga_dev_2019_2" = "FPGA Developer AMI - 1.8.*"
    "centos_7_aws_fpga_dev_2020_1" = "FPGA Developer AMI - 1.9.*"
    "centos_8"                     = "CentOS 8.* x86_64"
    "debian_9"                     = "debian-stretch-hvm-x86_64-gp2-*"
    "debian_10"                    = "debian-10-amd64-*"
    "fedora_31"                    = "Fedora-Cloud-Base-31-*"
    "fedora_32"                    = "Fedora-Cloud-Base-32-*"
    "ubuntu_16_04"                 = "ubuntu/images/ebs-ssd/ubuntu-xenial-16.04-amd64-server-*"
    "ubuntu_18_04"                 = "ubuntu/images/hvm-ssd/ubuntu-bionic-18.04-amd64-server-*"
    "ubuntu_20_04"                 = "ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"
  }

  # Remote user
  user = local.ami_users[var.image]
}

data "aws_ami" "image" {
  most_recent = true
  owners      = [local.ami_owners[var.image]]
  filter {
    name   = "name"
    values = [local.ami_names[var.image]]
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

# Configure security
resource "aws_key_pair" "key_pair" {
  key_name   = local.name
  public_key = local.public_key
}

resource "aws_security_group" "security_group" {
  name = local.name
  dynamic "ingress" {
    for_each = local.firewall_rules
    content {
      from_port        = ingress.value.port
      to_port          = ingress.value.port
      protocol         = ingress.value.protocol
      cidr_blocks      = ingress.value.cidr_blocks
      ipv6_cidr_blocks = ingress.value.ipv6_cidr_blocks
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Configure instance
resource "aws_spot_instance_request" "spot_instance" {
  ami                  = data.aws_ami.image.id
  instance_type        = var.instance_type
  security_groups      = [aws_security_group.security_group.name]
  key_name             = aws_key_pair.key_pair.key_name
  tags = {
    Name = local.name
  }
  root_block_device {
    delete_on_termination = true
  }

  # Spot specific
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

  # Instance configuration
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
    # Configure using Ansible
    command = "${local.ansible} -i '${self.public_ip},'"
  }
}

resource "aws_instance" "instance" {
  ami                  = data.aws_ami.image.id
  instance_type        = var.instance_type
  security_groups      = [aws_security_group.security_group.name]
  key_name             = aws_key_pair.key_pair.key_name
  tags = {
    Name = local.name
  }
  root_block_device {
    delete_on_termination = true
  }

  # On-demand specific
  count                                = var.spot ? 0 : 1
  instance_initiated_shutdown_behavior = "terminate"

  # Instance configuration
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
    # Configure using Ansible
    command = "${local.ansible} -i '${self.public_ip},'"
  }
}

locals {
  _instances = var.spot ? aws_spot_instance_request.spot_instance : aws_instance.instance
  # IP address, needs to hande the case instance was terminated by timeout
  ip_address = length(local._instances) > 0 ? lookup(local._instances[0], "public_ip") : null
}
