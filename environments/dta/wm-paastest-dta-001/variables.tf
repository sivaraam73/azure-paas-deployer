# ===========================================================================
# This file is identical across all server instances — do not edit.
# All values are controlled via terraform.tfvars.
# ===========================================================================

variable "subscription_id" {
  type      = string
  sensitive = true
}

variable "tenant_id" {
  type      = string
  sensitive = true
}

variable "environment" {
  type = string
}

variable "project" {
  type = string
}

variable "pg_resource_group_name" {
  type = string
}

variable "vnet_name" {
  type = string
}

variable "vnet_resource_group_name" {
  type = string
}

variable "pe_subnet_name" {
  type = string
}

variable "private_dns_zone_name" {
  type    = string
  default = "privatelink.postgres.database.azure.com"
}

variable "private_dns_zone_resource_group_name" {
  type = string
}

variable "pg_server_name" {
  type = string
}

variable "pg_version" {
  type    = number
  default = 16
}

variable "pg_sku_name" {
  type    = string
  default = "GP_Standard_D2ds_v5"
}

variable "pg_storage_mb" {
  type    = number
  default = 32768
}

variable "pg_storage_tier" {
  type    = string
  default = null
}

variable "pg_zone" {
  type    = number
  default = 1
}

variable "pg_auto_grow_enabled" {
  type    = bool
  default = false
}

variable "pg_admin_login" {
  type    = string
  default = "psqladmin"
}

variable "pg_admin_password" {
  type      = string
  sensitive = true
}

variable "pg_backup_retention_days" {
  type    = number
  default = 7
}

variable "pg_geo_redundant_backup_enabled" {
  type    = bool
  default = false
}

variable "pg_maintenance_window" {
  type = object({
    day_of_week  = number
    start_hour   = number
    start_minute = number
  })
  default = {
    day_of_week  = 0
    start_hour   = 2
    start_minute = 0
  }
}

variable "pg_ha_enabled" {
  type    = bool
  default = false
}

variable "pg_ha_standby_zone" {
  type    = number
  default = 2
}

variable "pg_databases" {
  type = map(object({
    name      = string
    charset   = optional(string, "UTF8")
    collation = optional(string, "en_US.utf8")
  }))
  default = {}
}
