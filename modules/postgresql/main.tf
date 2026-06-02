# ===========================================================================
# DATA SOURCES — reference pre-existing shared infrastructure
# ===========================================================================

data "azurerm_resource_group" "pg" {
  name = var.pg_resource_group_name
}

data "azurerm_virtual_network" "shared" {
  name                = var.vnet_name
  resource_group_name = var.vnet_resource_group_name
}

data "azurerm_subnet" "private_endpoint" {
  name                 = var.pe_subnet_name
  virtual_network_name = data.azurerm_virtual_network.shared.name
  resource_group_name  = var.vnet_resource_group_name
}

data "azurerm_private_dns_zone" "postgresql" {
  name                = var.private_dns_zone_name
  resource_group_name = var.private_dns_zone_resource_group_name
}

# ===========================================================================
# LOCALS
# ===========================================================================

locals {
  common_tags = {
    environment = var.environment
    managed_by  = "terraform"
    project     = var.project
  }
}

# ===========================================================================
# POSTGRESQL FLEXIBLE SERVER
# ===========================================================================

module "postgresql" {
  source  = "Azure/avm-res-dbforpostgresql-flexibleserver/azurerm"
  version = "0.2.2"

  name                = var.pg_server_name
  location            = data.azurerm_resource_group.pg.location
  resource_group_name = data.azurerm_resource_group.pg.name

  sku_name       = var.pg_sku_name
  server_version = var.pg_version
  storage_mb     = var.pg_storage_mb
  storage_tier   = var.pg_storage_tier
  zone           = var.pg_zone

  auto_grow_enabled = var.pg_auto_grow_enabled

  administrator_login    = var.pg_admin_login
  administrator_password = var.pg_admin_password

  backup_retention_days        = var.pg_backup_retention_days
  geo_redundant_backup_enabled = var.pg_geo_redundant_backup_enabled

  maintenance_window = {
    day_of_week  = var.pg_maintenance_window.day_of_week
    start_hour   = var.pg_maintenance_window.start_hour
    start_minute = var.pg_maintenance_window.start_minute
  }

  high_availability = var.pg_ha_enabled ? {
    mode                      = "ZoneRedundant"
    standby_availability_zone = var.pg_ha_standby_zone
  } : null

  private_endpoints = {
    primary = {
      subnet_resource_id            = data.azurerm_subnet.private_endpoint.id
      private_dns_zone_resource_ids = toset([data.azurerm_private_dns_zone.postgresql.id])
      private_dns_zone_group_name   = "default"
    }
  }

  databases = var.pg_databases
  tags      = local.common_tags

  enable_telemetry = false
}
