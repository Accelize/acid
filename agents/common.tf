/*
Common Terraform configuration
*/

variable "name" {
  type        = string
  description = "Agent name."
}

variable "ansiblePlaybook" {
  type        = string
  default     = "playbook.yml"
  description = "Ansible playbook."
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
    cidr_blocks = ["${chomp(data.http.public_ip.body)}/32"]
    }
  ]
  # Ansible-playbook CLI
  ansible = <<-EOF
    ANSIBLE_SSH_ARGS="-o ControlMaster=auto -o ControlPersist=60s -o PreferredAuthentications=publickey" \
    ANSIBLE_PIPELINING="True" ANSIBLE_HOST_KEY_CHECKING="False" ANSIBLE_SSH_RETRIES="3" \
    ANSIBLE_FORCE_COLOR="True" ANSIBLE_NOCOLOR="False" \
    ANSIBLE_DEPRECATION_WARNINGS="False" ANSIBLE_ACTION_WARNINGS="False" \
    ANSIBLE_DISPLAY_SKIPPED_HOSTS="False" ANSIBLE_STDOUT_CALLBACK="debug" \
    ansible-playbook ${var.ansiblePlaybook} -u ${local.user} \
    --private-key '${local_file.ssh_key_file.filename}' \
  EOF
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
