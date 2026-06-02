terraform {
  required_version = ">= 1.9, < 2.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.12"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.4"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stttfstatesiva001"
    container_name       = "tfstate"
    # UPDATE THIS — must be unique per server instance
    # Format: <environment>/<server-name>.tfstate
    # Example: dta/psql-myapp-dta-001.tfstate
    key = "dta/psql-CHANGEME.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}
