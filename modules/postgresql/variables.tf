# ===========================================================================
# IDENTITY & ENVIRONMENT
# ===========================================================================

variable "subscription_id" {
  description = "Azure Subscription ID"
  type        = string
  sensitive   = true
}

variable "tenant_id" {
  description = "Azure Tenant ID"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment label applied to all tags (dta / prod)"
  type        = string
}

variable "project" {
  description = "Project name applied to all tags"
  type        = string
}

# ===========================================================================
# RESOURCE GROUP
# ===========================================================================

variable "pg_resource_group_name" {
  description = "Name of the pre-existing resource group where the PostgreSQL server will be created"
  type        = string
}

# ===========================================================================
# NETWORKING
# ===========================================================================

variable "vnet_name" {
  description = "Name of the pre-existing shared Virtual Network"
  type        = string
}

variable "vnet_resource_group_name" {
  description = "Resource group of the pre-existing shared Virtual Network"
  type        = string
}

variable "pe_subnet_name" {
  description = "Name of the pre-existing subnet used for the Private Endpoint NIC"
  type        = string
}

variable "private_dns_zone_name" {
  description = "Name of the pre-existing Private DNS Zone"
  type        = string
  default     = "privatelink.postgres.database.azure.com"
}

variable "private_dns_zone_resource_group_name" {
  description = "Resource group of the pre-existing Private DNS Zone"
  type        = string
}

# ===========================================================================
# POSTGRESQL SERVER
# ===========================================================================

variable "pg_server_name" {
  description = "Name of the PostgreSQL Flexible Server (must be globally unique)"
  type        = string
}

variable "pg_version" {
  description = "PostgreSQL major version. Supported: 14, 15, 16, 17"
  type        = number
  default     = 16

  validation {
    condition     = contains([14, 15, 16, 17], var.pg_version)
    error_message = "pg_version must be 14, 15, 16, or 17."
  }
}

variable "pg_sku_name" {
  description = <<-EOT
    Server SKU — controls vCPUs and memory.
    Recommended: v5 series (current generation, long-term supported).
    Avoid v3 series for new deployments (no reserved pricing after July 2026).

    Burstable (dev/test only — shared CPU, not for production):
      B_Standard_B1ms  =  1 vCPU,  2 GB RAM
      B_Standard_B2ms  =  2 vCPU,  8 GB RAM
      B_Standard_B4ms  =  4 vCPU, 16 GB RAM
      B_Standard_B8ms  =  8 vCPU, 32 GB RAM

    General Purpose v5 — 4 GB RAM per vCPU (recommended for most workloads):
      GP_Standard_D2ds_v5  =  2 vCPU,   8 GB RAM
      GP_Standard_D4ds_v5  =  4 vCPU,  16 GB RAM
      GP_Standard_D8ds_v5  =  8 vCPU,  32 GB RAM
      GP_Standard_D16ds_v5 = 16 vCPU,  64 GB RAM
      GP_Standard_D32ds_v5 = 32 vCPU, 128 GB RAM
      GP_Standard_D48ds_v5 = 48 vCPU, 192 GB RAM
      GP_Standard_D64ds_v5 = 64 vCPU, 256 GB RAM
      GP_Standard_D96ds_v5 = 96 vCPU, 384 GB RAM

    Memory Optimized v5 — 8 GB RAM per vCPU (high memory workloads):
      MO_Standard_E2ds_v5  =  2 vCPU,  16 GB RAM
      MO_Standard_E4ds_v5  =  4 vCPU,  32 GB RAM
      MO_Standard_E8ds_v5  =  8 vCPU,  64 GB RAM
      MO_Standard_E16ds_v5 = 16 vCPU, 128 GB RAM
      MO_Standard_E32ds_v5 = 32 vCPU, 256 GB RAM
      MO_Standard_E48ds_v5 = 48 vCPU, 384 GB RAM
      MO_Standard_E64ds_v5 = 64 vCPU, 512 GB RAM
      MO_Standard_E96ds_v5 = 96 vCPU, 672 GB RAM
  EOT
  type    = string
  default = "GP_Standard_D2ds_v5"
}

variable "pg_storage_mb" {
  description = <<-EOT
    Disk size in MB — controls how much data the server can store.
      32768   =  32 GB
      65536   =  64 GB
      131072  = 128 GB
      262144  = 256 GB
      524288  = 512 GB
      1048576 =   1 TB
      2097152 =   2 TB
      4194304 =   4 TB
  EOT
  type    = number
  default = 32768

  validation {
    condition     = contains([32768, 65536, 131072, 262144, 524288, 1048576, 2097152, 4194304], var.pg_storage_mb)
    error_message = "pg_storage_mb must be one of: 32768, 65536, 131072, 262144, 524288, 1048576, 2097152, 4194304."
  }
}

variable "pg_storage_tier" {
  description = <<-EOT
    Storage performance tier — controls IOPS and throughput.
    Leave as null to let Azure auto-select based on storage size.
      P4   =   120 IOPS  ( 32 GB)
      P6   =   240 IOPS  ( 64 GB)
      P10  =   500 IOPS  (128 GB)
      P15  =  1100 IOPS  (256 GB)
      P20  =  2300 IOPS  (512 GB)
      P30  =  5000 IOPS  (  1 TB)
      P40  =  7500 IOPS  (  2 TB)
      P50  =  7500 IOPS  (  4 TB)
  EOT
  type    = string
  default = null
}

variable "pg_zone" {
  description = "Availability zone for the primary server (1, 2, or 3)"
  type        = number
  default     = 1

  validation {
    condition     = contains([1, 2, 3], var.pg_zone)
    error_message = "pg_zone must be 1, 2, or 3."
  }
}

variable "pg_auto_grow_enabled" {
  description = "Enable storage auto-grow. Recommended true for production."
  type        = bool
  default     = false
}

# ===========================================================================
# ADMINISTRATOR CREDENTIALS
# ===========================================================================

variable "pg_admin_login" {
  description = "Administrator username for the PostgreSQL server"
  type        = string
  default     = "psqladmin"
}

variable "pg_admin_password" {
  description = "Administrator password. Inject via TF_VAR_pg_admin_password env var. Never store in tfvars."
  type        = string
  sensitive   = true
}

# ===========================================================================
# BACKUP
# ===========================================================================

variable "pg_backup_retention_days" {
  description = "Backup retention period in days. Between 7 and 35."
  type        = number
  default     = 7

  validation {
    condition     = var.pg_backup_retention_days >= 7 && var.pg_backup_retention_days <= 35
    error_message = "pg_backup_retention_days must be between 7 and 35."
  }
}

variable "pg_geo_redundant_backup_enabled" {
  description = "Enable geo-redundant backups. Cannot be changed after server creation."
  type        = bool
  default     = false
}

# ===========================================================================
# MAINTENANCE WINDOW
# ===========================================================================

variable "pg_maintenance_window" {
  description = "Preferred maintenance window (UTC). day_of_week: 0=Sunday, 6=Saturday."
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

  validation {
    condition     = var.pg_maintenance_window.day_of_week >= 0 && var.pg_maintenance_window.day_of_week <= 6
    error_message = "day_of_week must be between 0 (Sunday) and 6 (Saturday)."
  }

  validation {
    condition     = var.pg_maintenance_window.start_hour >= 0 && var.pg_maintenance_window.start_hour <= 23
    error_message = "start_hour must be between 0 and 23."
  }

  validation {
    condition     = contains([0, 30], var.pg_maintenance_window.start_minute)
    error_message = "start_minute must be 0 or 30."
  }
}

# ===========================================================================
# HIGH AVAILABILITY
# ===========================================================================

variable "pg_ha_enabled" {
  description = "Enable Zone-Redundant High Availability. Recommended for production."
  type        = bool
  default     = false
}

variable "pg_ha_standby_zone" {
  description = "Availability zone for the HA standby replica. Must differ from pg_zone."
  type        = number
  default     = 2

  validation {
    condition     = contains([1, 2, 3], var.pg_ha_standby_zone)
    error_message = "pg_ha_standby_zone must be 1, 2, or 3."
  }
}

# ===========================================================================
# DATABASES
# ===========================================================================

variable "pg_databases" {
  description = "Map of PostgreSQL databases to create on the server."
  type = map(object({
    name      = string
    charset   = optional(string, "UTF8")
    collation = optional(string, "en_US.utf8")
  }))
  default = {}
}