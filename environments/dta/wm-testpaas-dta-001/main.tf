# ===========================================================================
# This file is identical across all server instances — do not edit.
# All values are controlled via terraform.tfvars.
# ===========================================================================

module "postgresql" {
  source = "../../../modules/postgresql"

  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  environment     = var.environment
  project         = var.project

  pg_resource_group_name = var.pg_resource_group_name

  vnet_name                            = var.vnet_name
  vnet_resource_group_name             = var.vnet_resource_group_name
  pe_subnet_name                       = var.pe_subnet_name
  private_dns_zone_name                = var.private_dns_zone_name
  private_dns_zone_resource_group_name = var.private_dns_zone_resource_group_name

  pg_server_name       = var.pg_server_name
  pg_version           = var.pg_version
  pg_sku_name          = var.pg_sku_name
  pg_storage_mb        = var.pg_storage_mb
  pg_storage_tier      = var.pg_storage_tier
  pg_zone              = var.pg_zone
  pg_auto_grow_enabled = var.pg_auto_grow_enabled

  pg_admin_login    = var.pg_admin_login
  pg_admin_password = var.pg_admin_password

  pg_backup_retention_days        = var.pg_backup_retention_days
  pg_geo_redundant_backup_enabled = var.pg_geo_redundant_backup_enabled

  pg_maintenance_window = var.pg_maintenance_window

  pg_ha_enabled      = var.pg_ha_enabled
  pg_ha_standby_zone = var.pg_ha_standby_zone

  pg_databases = var.pg_databases
}
