output "postgresql_server_id" {
  description = "Resource ID of the PostgreSQL Flexible Server"
  value       = module.postgresql.resource_id
}

output "postgresql_server_name" {
  description = "Name of the PostgreSQL Flexible Server"
  value       = var.pg_server_name
}

output "resource_group_name" {
  description = "Resource group where the PostgreSQL server was deployed"
  value       = data.azurerm_resource_group.pg.name
}

output "location" {
  description = "Azure region where the server was deployed"
  value       = data.azurerm_resource_group.pg.location
}
