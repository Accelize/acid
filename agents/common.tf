/*
Common Terraform configuration
*/

variable "name" {
  type        = string
  description = "Agent name."
}

variable "image" {
  type        = string
  default     = "ubuntu_18_04"
  description = "OS image."
}

variable "images" {
  type        = map(map(string))
  description = "Available images"
}

variable "volumeSize" {
  type        = number
  default     = null
  description = "Volume size. Default to image volume size."
}

locals {
  # Resources name
  name = var.name
  # Image information
  image = var.images[var.image]
  # SSH key
  private_key_path = "${path.module}/ssh_private.pem"
  private_key      = tls_private_key.ssh_key.private_key_pem
  public_key       = tls_private_key.ssh_key.public_key_openssh
  # Firewall configuration
  firewall_rules = [{
    # Allow SSH from agent running Ansible
    port        = 22,
    protocol    = "tcp",
    cidr_blocks = ["${chomp(data.http.public_ip.response_body)}/32"]
    }
  ]
}

data "http" "public_ip" {
  url = "https://api.ipify.org"
}

resource "tls_private_key" "ssh_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "local_file" "ssh_key_file" {
  content  = tls_private_key.ssh_key.private_key_pem
  filename = local.private_key_path
  provisioner "local-exec" {
    command = "chmod 600 ${self.filename}"
  }
}

output "ipAddress" {
  description = "Agent IP address"
  value       = local.ip_address
}
output "user" {
  description = "Agent user"
  value       = local.user
}
output "privateKey" {
  description = "Private key"
  value       = local.private_key_path
  sensitive   = true
}

output "imageVersion" {
  description = "Image version"
  value       = local.image_version
}

output "imageDefaultEnv" {
  description = "Image default agent environment"
  value       = lookup(local.image, "agentEnv", "{}")
}
