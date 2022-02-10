/*
Azure Compute Virtual Machines provider
*/

provider "azurerm" {
  features {}
}

variable "instanceType" {
  type        = string
  default     = "Standard_B1s"
  description = "Virtual machine size."
}

variable "spot" {
  type        = bool
  default     = true
  description = "Spot virtual machine."
}

variable "region" {
  type        = string
  default     = "West Europe"
  description = "Location."
}

variable "resourceGroupName" {
  type        = string
  default     = "acid"
  description = "Resource group name."
}

variable "virtualNetworkName" {
  type        = string
  default     = "acid"
  description = "Virtual network name"
}

data "azurerm_platform_image" "agent" {
  location  = var.region
  publisher = local.image["publisher"]
  offer     = local.image["offer"]
  sku       = local.image["sku"]
}

data "azurerm_virtual_network" "agent" {
  name                = var.virtualNetworkName
  resource_group_name = var.resourceGroupName
}

data "azurerm_subnet" "agent" {
  name                 = data.azurerm_virtual_network.agent.subnets.0
  virtual_network_name = var.virtualNetworkName
  resource_group_name  = var.resourceGroupName
}

resource "azurerm_public_ip" "agent" {
  name                = local.name
  resource_group_name = var.resourceGroupName
  location            = var.region
  allocation_method   = "Static"
}

resource "azurerm_network_interface" "agent" {
  name                = local.name
  resource_group_name = var.resourceGroupName
  location            = var.region
  ip_configuration {
    name                          = local.name
    subnet_id                     = data.azurerm_subnet.agent.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.agent.id
    primary                       = true
  }
}

resource "azurerm_network_security_group" "agent" {
  name                = local.name
  resource_group_name = var.resourceGroupName
  location            = var.region
  dynamic "security_rule" {
    for_each = local.firewall_rules
    content {
      name                       = "${local.name}-${security_rule.key}"
      priority                   = 100 + security_rule.key
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = title(security_rule.value.protocol)
      source_address_prefixes    = security_rule.value.cidr_blocks
      source_port_range          = "*"
      destination_address_prefix = "*"
      destination_port_range     = security_rule.value.port
    }
  }
}

resource "azurerm_network_interface_security_group_association" "agent" {
  network_interface_id      = azurerm_network_interface.agent.id
  network_security_group_id = azurerm_network_security_group.agent.id
}

resource "azurerm_linux_virtual_machine" "agent" {
  name                  = local.name
  resource_group_name   = var.resourceGroupName
  location              = var.region
  size                  = var.instanceType
  admin_username        = local.user
  network_interface_ids = [azurerm_network_interface.agent.id]
  source_image_reference {
    publisher = data.azurerm_platform_image.agent.publisher
    offer     = data.azurerm_platform_image.agent.offer
    sku       = data.azurerm_platform_image.agent.sku
    version   = data.azurerm_platform_image.agent.version
  }
  admin_ssh_key {
    username   = local.user
    public_key = local.public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = var.volumeSize
  }
  priority        = var.spot ? "Spot" : "Regular"
  eviction_policy = var.spot ? "Deallocate" : null

  provisioner "remote-exec" {
    # Wait until instance is ready
    inline = ["cd"]
    connection {
      host        = self.public_ip_address
      type        = "ssh"
      user        = local.user
      private_key = local.private_key
    }
  }
}

locals {
  ip_address    = azurerm_linux_virtual_machine.agent.public_ip_address
  user          = "azureuser"
  image_version = data.azurerm_platform_image.agent.version
}
