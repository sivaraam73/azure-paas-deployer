# ===========================================================================
# This file is identical across all server instances — do not edit.
# ===========================================================================

output "postgresql_server_id" {
  description = "Resource ID of the PostgreSQL Flexible Server"
  value       = module.postgresql.postgresql_server_id
}

output "postgresql_server_name" {
  description = "Name of the PostgreSQL Flexible Server"
  value       = module.postgresql.postgresql_server_name
}

output "resource_group_name" {
  description = "Resource group where the server was deployed"
  value       = module.postgresql.resource_group_name
}

output "location" {
  description = "Azure region where the server was deployed"
  value       = module.postgresql.location
}
