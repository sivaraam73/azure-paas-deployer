cat > ~/Github-Personal/azure-paas-test/pg_manager.py << 'ENDOFFILE'
#!/usr/bin/env python3
"""
pg_manager.py — PostgreSQL Flexible Server Manager
Automates branch creation, tfvars generation, and GitHub PR workflow.
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path

# ===========================================================================
# CONSTANTS
# ===========================================================================

SKU_OPTIONS = {
    "Burstable": [
        ("B_Standard_B1ms",  " 1 vCPU,  2 GB RAM  — dev/test only"),
        ("B_Standard_B2ms",  " 2 vCPU,  8 GB RAM  — dev/test only"),
        ("B_Standard_B4ms",  " 4 vCPU, 16 GB RAM  — dev/test only"),
        ("B_Standard_B8ms",  " 8 vCPU, 32 GB RAM  — dev/test only"),
    ],
    "GeneralPurpose": [
        ("GP_Standard_D2ds_v5",  " 2 vCPU,   8 GB RAM"),
        ("GP_Standard_D4ds_v5",  " 4 vCPU,  16 GB RAM"),
        ("GP_Standard_D8ds_v5",  " 8 vCPU,  32 GB RAM"),
        ("GP_Standard_D16ds_v5", "16 vCPU,  64 GB RAM"),
        ("GP_Standard_D32ds_v5", "32 vCPU, 128 GB RAM"),
        ("GP_Standard_D64ds_v5", "64 vCPU, 256 GB RAM"),
    ],
    "MemoryOptimized": [
        ("MO_Standard_E2ds_v5",  " 2 vCPU,  16 GB RAM"),
        ("MO_Standard_E4ds_v5",  " 4 vCPU,  32 GB RAM"),
        ("MO_Standard_E8ds_v5",  " 8 vCPU,  64 GB RAM"),
        ("MO_Standard_E16ds_v5", "16 vCPU, 128 GB RAM"),
        ("MO_Standard_E32ds_v5", "32 vCPU, 256 GB RAM"),
        ("MO_Standard_E64ds_v5", "64 vCPU, 512 GB RAM"),
    ],
}

STORAGE_OPTIONS = [
    (32768,   " 32 GB"),
    (65536,   " 64 GB"),
    (131072,  "128 GB"),
    (262144,  "256 GB"),
    (524288,  "512 GB"),
    (1048576, "  1 TB"),
    (2097152, "  2 TB"),
    (4194304, "  4 TB"),
]

PG_VERSIONS     = [14, 15, 16, 17]
ZONES           = [1, 2, 3]
ENVIRONMENTS    = ["dta", "prod"]
DAYS_OF_WEEK    = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
START_MINUTES   = [0, 30]

# ===========================================================================
# HELPERS
# ===========================================================================

def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_step(msg):
    print(f"\n  → {msg}")


def print_success(msg):
    print(f"  ✓ {msg}")


def print_error(msg):
    print(f"  ✗ {msg}")


def run_command(cmd, cwd=None, capture=True):
    """Run a shell command and return (success, output)."""
    result = subprocess.run(
        cmd, shell=True, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if capture:
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    return result.returncode == 0, "", ""


def get_repo_root():
    """Return the root directory of the repo."""
    return Path(__file__).parent.resolve()


def get_az_account():
    """Read subscription and tenant ID from az account show."""
    print_step("Reading Azure account details...")
    ok, out, err = run_command("az account show --output json")
    if not ok:
        print_error("Failed to read Azure account. Are you logged in via 'az login'?")
        sys.exit(1)
    data = json.loads(out)
    subscription_id = data["id"]
    tenant_id       = data["tenantId"]
    print_success(f"Subscription : {subscription_id}")
    print_success(f"Tenant       : {tenant_id}")
    return subscription_id, tenant_id


def get_github_remote(repo_root):
    """Get the GitHub remote URL and derive the repo path."""
    ok, out, _ = run_command("git remote get-url origin", cwd=repo_root)
    if not ok or not out:
        print_error("Could not determine GitHub remote URL.")
        sys.exit(1)
    # Handle both SSH and HTTPS formats
    # git@github.com:user/repo.git  or  https://github.com/user/repo.git
    match = re.search(r'[:/]([^:/]+/[^/]+?)(?:\.git)?$', out)
    if not match:
        print_error(f"Could not parse remote URL: {out}")
        sys.exit(1)
    return match.group(1)  # e.g. sivaraam73/azure-paas-test


def validate_input(prompt, pattern, example, error_msg, default=None, min_len=1, max_len=100):
    """Prompt until input matches pattern."""
    default_hint = f" (default={default})" if default is not None else ""
    print(f"\n  Format  : {error_msg}")
    print(f"  Example : {example}")
    while True:
        value = input(f"  Enter value{default_hint}: ").strip()
        if value == "" and default is not None:
            print_success(f"Using default: {default}")
            return default
        if value == "":
            print_error("Cannot be empty.")
            continue
        if len(value) < min_len or len(value) > max_len:
            print_error(f"Length must be between {min_len} and {max_len} characters.")
            continue
        if not re.match(pattern, value):
            print_error(f"{error_msg}")
            continue
        print_success(f"Accepted: {value}")
        return value


def select_option(prompt, options, default=None):
    """Display a numbered menu and return the selected value."""
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        if isinstance(opt, tuple):
            label = f"{opt[0]}  —  {opt[1]}"
            value = opt[0]
        else:
            label = str(opt)
            value = opt
        marker = " (default)" if (default is not None and value == default) else ""
        print(f"    {i}) {label}{marker}")
    while True:
        choice = input(f"  Enter choice [1-{len(options)}]: ").strip()
        if choice == "" and default is not None:
            for opt in options:
                v = opt[0] if isinstance(opt, tuple) else opt
                if v == default:
                    print_success(f"Using default: {default}")
                    return default
        if not choice.isdigit() or not (1 <= int(choice) <= len(options)):
            print_error(f"Enter a number between 1 and {len(options)}.")
            continue
        selected = options[int(choice) - 1]
        value = selected[0] if isinstance(selected, tuple) else selected
        print_success(f"Selected: {value}")
        return value


def confirm(prompt, default="n"):
    """Ask a yes/no question."""
    hint = "[y/N]" if default == "n" else "[Y/n]"
    while True:
        ans = input(f"\n  {prompt} {hint}: ").strip().lower()
        if ans == "":
            ans = default
        if ans in ["y", "yes"]:
            return True
        if ans in ["n", "no"]:
            return False
        print_error("Enter y or n.")


def collect_databases():
    """Collect one or more database names from the engineer."""
    print("\n  Databases to create on this server.")
    print("  Press Enter with empty name when done.")
    print("  Format  : lowercase letters, numbers and hyphens only")
    print("  Example : appdb")
    databases = {}
    while True:
        name = input(f"  Database name (or Enter to finish): ").strip()
        if name == "":
            if not databases:
                print_error("At least one database is required.")
                continue
            break
        if not re.match(r'^[a-z][a-z0-9_-]{1,62}$', name):
            print_error("Use lowercase letters, numbers, hyphens or underscores. Min 2 chars.")
            continue
        databases[name] = {
            "name":      name,
            "charset":   "UTF8",
            "collation": "en_US.utf8"
        }
        print_success(f"Added database: {name}")
    return databases


def git_pull(repo_root):
    print_step("Pulling latest from main...")
    ok, _, err = run_command("git checkout main", cwd=repo_root)
    if not ok:
        print_error(f"Failed to checkout main: {err}")
        sys.exit(1)
    ok, _, err = run_command("git pull origin main", cwd=repo_root)
    if not ok:
        print_error(f"Failed to pull: {err}")
        sys.exit(1)
    print_success("Up to date with main.")


def git_create_branch(repo_root, branch_name):
    print_step(f"Creating branch: {branch_name}")
    ok, _, err = run_command(f"git checkout -b {branch_name}", cwd=repo_root)
    if not ok:
        print_error(f"Failed to create branch: {err}")
        sys.exit(1)
    print_success(f"Branch created: {branch_name}")


def git_push_branch(repo_root, branch_name):
    print_step(f"Pushing branch: {branch_name}")
    ok, _, err = run_command(f"git push origin {branch_name}", cwd=repo_root)
    if not ok:
        print_error(f"Failed to push: {err}")
        sys.exit(1)
    print_success("Branch pushed.")


def print_pr_instructions(repo_slug, branch_name, server_name, action):
    """Print next steps after push."""
    pr_url = f"https://github.com/{repo_slug}/pull/new/{branch_name}"
    print("\n" + "=" * 60)
    print("  NEXT STEPS")
    print("=" * 60)
    print(f"\n  1. Create Pull Request:")
    print(f"     {pr_url}")
    print(f"\n  2. Get PR reviewed and approved by your team.")
    if action == "create":
        print(f"\n  3. After merge, deploy the server:")
        print(f"     cd environments/dta/{server_name}")
        print(f"     export TF_VAR_pg_admin_password='YourSecureP@ssword123!'")
        print(f"     terraform init")
        print(f"     terraform apply -var-file=\"terraform.tfvars\"")
        print(f"\n  4. After apply, add Azure resource lock:")
        print(f"     az lock create \\")
        print(f"       --name lock-{server_name} \\")
        print(f"       --resource-group <your-rg> \\")
        print(f"       --resource-type Microsoft.DBforPostgreSQL/flexibleServers \\")
        print(f"       --resource {server_name} \\")
        print(f"       --lock-type CanNotDelete")
    elif action == "modify":
        print(f"\n  3. After merge, apply changes:")
        print(f"     cd environments/dta/{server_name}")
        print(f"     export TF_VAR_pg_admin_password='YourSecureP@ssword123!'")
        print(f"     terraform apply -var-file=\"terraform.tfvars\"")
    elif action == "delete":
        print(f"\n  3. After merge, remove Azure lock then destroy:")
        print(f"     az lock delete \\")
        print(f"       --name lock-{server_name} \\")
        print(f"       --resource-group <your-rg> \\")
        print(f"       --resource-type Microsoft.DBforPostgreSQL/flexibleServers \\")
        print(f"       --resource {server_name}")
        print(f"     cd environments/dta/{server_name}")
        print(f"     export TF_VAR_pg_admin_password='YourSecureP@ssword123!'")
        print(f"     terraform destroy -var-file=\"terraform.tfvars\"")
    print()


# ===========================================================================
# TFVARS WRITER
# ===========================================================================

def write_tfvars(path, data):
    """Write terraform.tfvars from collected data."""
    db_block = ""
    for db in data["databases"].values():
        db_block += f"""  {db["name"]} = {{
    name      = "{db["name"]}"
    charset   = "UTF8"
    collation = "en_US.utf8"
  }}
"""
    content = f"""# ===========================================================================
# terraform.tfvars — {data["server_name"]}
# Generated by pg_manager.py — do not edit manually
# ===========================================================================

# Identity & Environment
subscription_id = "{data["subscription_id"]}"
tenant_id       = "{data["tenant_id"]}"
environment     = "{data["environment"]}"
project         = "{data["project"]}"

# Resource Group
pg_resource_group_name = "{data["pg_resource_group_name"]}"

# Networking
vnet_name                            = "{data["vnet_name"]}"
vnet_resource_group_name             = "{data["vnet_resource_group_name"]}"
pe_subnet_name                       = "{data["pe_subnet_name"]}"
private_dns_zone_name                = "privatelink.postgres.database.azure.com"
private_dns_zone_resource_group_name = "{data["private_dns_zone_resource_group_name"]}"

# PostgreSQL Server
pg_server_name       = "{data["server_name"]}"
pg_version           = {data["pg_version"]}
pg_sku_name          = "{data["pg_sku_name"]}"
pg_storage_mb        = {data["pg_storage_mb"]}
pg_storage_tier      = null
pg_auto_grow_enabled = {str(data["pg_auto_grow_enabled"]).lower()}
pg_zone              = {data["pg_zone"]}

# Administrator
pg_admin_login = "{data["pg_admin_login"]}"

# Backup
pg_backup_retention_days        = {data["pg_backup_retention_days"]}
pg_geo_redundant_backup_enabled = {str(data["pg_geo_redundant_backup_enabled"]).lower()}

# Maintenance Window
pg_maintenance_window = {{
  day_of_week  = {data["maintenance_day"]}
  start_hour   = {data["maintenance_hour"]}
  start_minute = {data["maintenance_minute"]}
}}

# High Availability
pg_ha_enabled      = {str(data["pg_ha_enabled"]).lower()}
pg_ha_standby_zone = {data["pg_ha_standby_zone"]}

# Databases
pg_databases = {{
{db_block}}}
"""
    with open(path, "w") as f:
        f.write(content)


def write_global_tf(path, environment, server_name, storage_account):
    """Write 00_global.tf with correct backend key."""
    content = f"""terraform {{
  required_version = ">= 1.9, < 2.0"

  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = "~> 4.12"
    }}
    azapi = {{
      source  = "Azure/azapi"
      version = "~> 2.4"
    }}
  }}

  backend "azurerm" {{
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "{storage_account}"
    container_name       = "tfstate"
    key                  = "{environment}/{server_name}.tfstate"
  }}
}}

provider "azurerm" {{
  features {{}}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}}
"""
    with open(path, "w") as f:
        f.write(content)


# ===========================================================================
# INPUT COLLECTION
# ===========================================================================

def collect_server_inputs(subscription_id, tenant_id, existing_data=None):
    """Collect all inputs for a server. If existing_data provided, use as defaults."""
    e = existing_data or {}
    data = {}
    data["subscription_id"] = subscription_id
    data["tenant_id"]       = tenant_id

    print_header("Environment")
    data["environment"] = select_option(
        "Select environment:",
        ENVIRONMENTS,
        default=e.get("environment", "dta")
    )

    print_header("Project Details")
    print("\n  Project name:")
    data["project"] = validate_input(
        "Project name",
        r'^[a-z][a-z0-9-]{1,18}[a-z0-9]$',
        "myapp",
        "Lowercase letters, numbers and hyphens only. 3-20 chars.",
        default=e.get("project"),
        min_len=3, max_len=20
    )

    print("\n  Server name (must be globally unique across all of Azure):")
    data["server_name"] = validate_input(
        "Server name",
        r'^[a-z][a-z0-9-]{1,61}[a-z0-9]$',
        f"psql-{data['project']}-{data['environment']}-001",
        "Lowercase letters, numbers and hyphens only. 3-63 chars.",
        default=e.get("server_name"),
        min_len=3, max_len=63
    )

    print_header("Resource Group")
    print("\n  Resource group where the PostgreSQL server will be created:")
    data["pg_resource_group_name"] = validate_input(
        "Resource group",
        r'^[a-zA-Z0-9._-]{1,90}$',
        "rg-myapp-dta",
        "Letters, numbers, hyphens, underscores and periods only.",
        default=e.get("pg_resource_group_name"),
        min_len=1, max_len=90
    )

    print_header("Networking")
    print("\n  VNet name:")
    data["vnet_name"] = validate_input(
        "VNet name",
        r'^[a-zA-Z0-9._-]{2,64}$',
        "vnet-shared-dta",
        "Letters, numbers, hyphens, underscores and periods only.",
        default=e.get("vnet_name"),
        min_len=2, max_len=64
    )

    print("\n  VNet resource group:")
    data["vnet_resource_group_name"] = validate_input(
        "VNet resource group",
        r'^[a-zA-Z0-9._-]{1,90}$',
        "rg-network-dta",
        "Letters, numbers, hyphens, underscores and periods only.",
        default=e.get("vnet_resource_group_name"),
        min_len=1, max_len=90
    )

    print("\n  Private endpoint subnet name:")
    data["pe_subnet_name"] = validate_input(
        "PE subnet name",
        r'^[a-zA-Z0-9._-]{2,80}$',
        "snet-private-endpoints",
        "Letters, numbers, hyphens, underscores and periods only.",
        default=e.get("pe_subnet_name"),
        min_len=2, max_len=80
    )

    print("\n  Private DNS zone resource group:")
    data["private_dns_zone_resource_group_name"] = validate_input(
        "DNS zone resource group",
        r'^[a-zA-Z0-9._-]{1,90}$',
        "rg-network-dta",
        "Letters, numbers, hyphens, underscores and periods only.",
        default=e.get("private_dns_zone_resource_group_name"),
        min_len=1, max_len=90
    )

    print_header("PostgreSQL Server")
    data["pg_version"] = select_option(
        "PostgreSQL version:",
        PG_VERSIONS,
        default=e.get("pg_version", 16)
    )

    tier = select_option(
        "SKU tier:",
        list(SKU_OPTIONS.keys()),
        default="GeneralPurpose"
    )
    data["pg_sku_name"] = select_option(
        "SKU size:",
        SKU_OPTIONS[tier],
        default=e.get("pg_sku_name")
    )

    data["pg_storage_mb"] = select_option(
        "Storage size:",
        STORAGE_OPTIONS,
        default=e.get("pg_storage_mb", 32768)
    )

    data["pg_zone"] = select_option(
        "Availability zone:",
        ZONES,
        default=e.get("pg_zone", 1)
    )

    data["pg_auto_grow_enabled"] = confirm(
        "Enable storage auto-grow? (recommended for prod)",
        default="n"
    )

    print_header("Administrator")
    print("\n  Admin login username:")
    data["pg_admin_login"] = validate_input(
        "Admin login",
        r'^[a-zA-Z][a-zA-Z0-9_]{1,62}$',
        "psqladmin",
        "Letters, numbers and underscores. Must start with a letter. 2-63 chars.",
        default=e.get("pg_admin_login", "psqladmin"),
        min_len=2, max_len=63
    )

    print_header("Backup")
    print("\n  Backup retention days (7-35):")
    while True:
        val = input(f"  Enter value (default={e.get('pg_backup_retention_days', 7)}): ").strip()
        if val == "":
            data["pg_backup_retention_days"] = e.get("pg_backup_retention_days", 7)
            print_success(f"Using: {data['pg_backup_retention_days']}")
            break
        if val.isdigit() and 7 <= int(val) <= 35:
            data["pg_backup_retention_days"] = int(val)
            print_success(f"Accepted: {val}")
            break
        print_error("Enter a number between 7 and 35.")

    data["pg_geo_redundant_backup_enabled"] = confirm(
        "Enable geo-redundant backup? (recommended for prod)",
        default="n"
    )

    print_header("Maintenance Window")
    data["maintenance_day"] = DAYS_OF_WEEK.index(select_option(
        "Maintenance day:",
        DAYS_OF_WEEK,
        default=DAYS_OF_WEEK[e.get("maintenance_day", 0)]
    ))

    print("\n  Maintenance start hour (0-23 UTC):")
    while True:
        val = input(f"  Enter value (default={e.get('maintenance_hour', 2)}): ").strip()
        if val == "":
            data["maintenance_hour"] = e.get("maintenance_hour", 2)
            print_success(f"Using: {data['maintenance_hour']}")
            break
        if val.isdigit() and 0 <= int(val) <= 23:
            data["maintenance_hour"] = int(val)
            print_success(f"Accepted: {val}")
            break
        print_error("Enter a number between 0 and 23.")

    data["maintenance_minute"] = select_option(
        "Maintenance start minute:",
        START_MINUTES,
        default=e.get("maintenance_minute", 0)
    )

    print_header("High Availability")
    data["pg_ha_enabled"] = confirm(
        "Enable Zone-Redundant High Availability? (recommended for prod)",
        default="n"
    )
    if data["pg_ha_enabled"]:
        available_zones = [z for z in ZONES if z != data["pg_zone"]]
        data["pg_ha_standby_zone"] = select_option(
            "Standby availability zone (must differ from primary):",
            available_zones,
            default=available_zones[0]
        )
    else:
        data["pg_ha_standby_zone"] = 2 if data["pg_zone"] != 2 else 3

    print_header("Databases")
    data["databases"] = collect_databases()

    return data


def print_summary(data):
    """Print a summary of all collected inputs."""
    print_header("SUMMARY — Please review before proceeding")
    print(f"""
  Environment     : {data['environment']}
  Project         : {data['project']}
  Server name     : {data['server_name']}

  Resource Group  : {data['pg_resource_group_name']}
  VNet            : {data['vnet_name']} ({data['vnet_resource_group_name']})
  PE Subnet       : {data['pe_subnet_name']}
  DNS Zone RG     : {data['private_dns_zone_resource_group_name']}

  PG Version      : {data['pg_version']}
  SKU             : {data['pg_sku_name']}
  Storage         : {data['pg_storage_mb']} MB
  Zone            : {data['pg_zone']}
  Auto Grow       : {data['pg_auto_grow_enabled']}
  Admin Login     : {data['pg_admin_login']}

  Backup Retention: {data['pg_backup_retention_days']} days
  Geo Redundant   : {data['pg_geo_redundant_backup_enabled']}

  Maintenance     : {DAYS_OF_WEEK[data['maintenance_day']]} {data['maintenance_hour']:02d}:{data['maintenance_minute']:02d} UTC

  HA Enabled      : {data['pg_ha_enabled']}
  HA Standby Zone : {data['pg_ha_standby_zone']}

  Databases       : {', '.join(data['databases'].keys())}

  Subscription ID : {data['subscription_id']}
  Tenant ID       : {data['tenant_id']}
    """)


# ===========================================================================
# READ EXISTING TFVARS
# ===========================================================================

def read_existing_tfvars(tfvars_path):
    """Parse existing tfvars into a dict for use as defaults in modify flow."""
    data = {}
    if not tfvars_path.exists():
        return data
    content = tfvars_path.read_text()

    def extract(key, cast=str):
        match = re.search(rf'^{key}\s*=\s*"?([^"\n]+)"?', content, re.MULTILINE)
        if match:
            val = match.group(1).strip()
            try:
                return cast(val)
            except:
                return val
        return None

    data["environment"]                          = extract("environment")
    data["project"]                              = extract("project")
    data["server_name"]                          = extract("pg_server_name")
    data["pg_resource_group_name"]               = extract("pg_resource_group_name")
    data["vnet_name"]                            = extract("vnet_name")
    data["vnet_resource_group_name"]             = extract("vnet_resource_group_name")
    data["pe_subnet_name"]                       = extract("pe_subnet_name")
    data["private_dns_zone_resource_group_name"] = extract("private_dns_zone_resource_group_name")
    data["pg_version"]                           = extract("pg_version", int)
    data["pg_sku_name"]                          = extract("pg_sku_name")
    data["pg_storage_mb"]                        = extract("pg_storage_mb", int)
    data["pg_zone"]                              = extract("pg_zone", int)
    data["pg_admin_login"]                       = extract("pg_admin_login")
    data["pg_backup_retention_days"]             = extract("pg_backup_retention_days", int)
    data["maintenance_day"]                      = extract("day_of_week", int)
    data["maintenance_hour"]                     = extract("start_hour", int)
    data["maintenance_minute"]                   = extract("start_minute", int)

    for bool_key, tf_key in [
        ("pg_auto_grow_enabled",         "pg_auto_grow_enabled"),
        ("pg_geo_redundant_backup_enabled", "pg_geo_redundant_backup_enabled"),
        ("pg_ha_enabled",                "pg_ha_enabled"),
    ]:
        m = re.search(rf'^{tf_key}\s*=\s*(true|false)', content, re.MULTILINE)
        if m:
            data[bool_key] = m.group(1) == "true"

    data["pg_ha_standby_zone"] = extract("pg_ha_standby_zone", int)

    # Parse databases block
    db_matches = re.findall(r'name\s*=\s*"([^"]+)"', content)
    data["databases"] = {name: {"name": name, "charset": "UTF8", "collation": "en_US.utf8"}
                         for name in db_matches if name != "appdb" or True}
    return data


def list_servers(repo_root, environment=None):
    """List existing server folders."""
    servers = []
    env_path = repo_root / "environments"
    if environment:
        envs = [env_path / environment]
    else:
        envs = [p for p in env_path.iterdir() if p.is_dir()]
    for env_dir in envs:
        if env_dir.is_dir():
            for server_dir in sorted(env_dir.iterdir()):
                if server_dir.is_dir() and (server_dir / "terraform.tfvars").exists():
                    servers.append((env_dir.name, server_dir.name, server_dir))
    return servers


# ===========================================================================
# FLOWS
# ===========================================================================

def get_storage_account(repo_root):
    """Read storage account name from an existing 00_global.tf."""
    for env_dir in (repo_root / "environments").iterdir():
        for server_dir in env_dir.iterdir():
            tf = server_dir / "00_global.tf"
            if tf.exists():
                m = re.search(r'storage_account_name\s*=\s*"([^"]+)"', tf.read_text())
                if m:
                    return m.group(1)
    # Fall back to template
    tf = repo_root / "_template" / "00_global.tf"
    if tf.exists():
        m = re.search(r'storage_account_name\s*=\s*"([^"]+)"', tf.read_text())
        if m:
            return m.group(1)
    return "stttfstatesiva001"


def create_server(repo_root, repo_slug):
    print_header("CREATE NEW SERVER")
    subscription_id, tenant_id = get_az_account()
    storage_account = get_storage_account(repo_root)

    data = collect_server_inputs(subscription_id, tenant_id)
    print_summary(data)

    if not confirm("Proceed with these settings?", default="n"):
        print("\n  Cancelled.")
        return

    server_name = data["server_name"]
    environment = data["environment"]
    server_path = repo_root / "environments" / environment / server_name
    branch_name = f"add/{server_name}"

    if server_path.exists():
        print_error(f"Server folder already exists: {server_path}")
        return

    git_pull(repo_root)
    git_create_branch(repo_root, branch_name)

    # Copy template
    print_step(f"Creating server folder: {server_path}")
    import shutil
    shutil.copytree(repo_root / "_template", server_path)

    # Write files
    write_global_tf(
        server_path / "00_global.tf",
        environment, server_name, storage_account
    )
    write_tfvars(server_path / "terraform.tfvars", data)

    # Remove example tfvars from instance folder
    example = server_path / "terraform.tfvars.example"
    if example.exists():
        example.unlink()

    print_success(f"Server folder created: {server_path}")

    # Git commit and push
    ok, _, err = run_command(
        f'git add . && git commit -m "Add {server_name} PostgreSQL server"',
        cwd=repo_root
    )
    if not ok:
        print_error(f"Git commit failed: {err}")
        return

    git_push_branch(repo_root, branch_name)
    print_pr_instructions(repo_slug, branch_name, server_name, "create")


def modify_server(repo_root, repo_slug):
    print_header("MODIFY EXISTING SERVER")

    servers = list_servers(repo_root)
    if not servers:
        print_error("No existing servers found.")
        return

    print("\n  Select server to modify:")
    options = [f"{env}/{name}" for env, name, _ in servers]
    selected = select_option("Available servers:", options)
    env, name = selected.split("/")
    server_path = repo_root / "environments" / env / name

    print_step(f"Reading current configuration for: {name}")
    existing = read_existing_tfvars(server_path / "terraform.tfvars")

    print_header("MODIFY OPTIONS")
    print("""
  What would you like to modify?

    1) SKU (compute size)
    2) Storage size
    3) Backup retention days
    4) Geo redundant backup
    5) Maintenance window
    6) High availability
    7) Databases
    8) All fields
    9) Cancel
    """)

    while True:
        choice = input("  Enter choice [1-9]: ").strip()
        if choice in [str(i) for i in range(1, 10)]:
            break
        print_error("Enter a number between 1 and 9.")

    if choice == "9":
        print("\n  Cancelled.")
        return

    subscription_id, tenant_id = get_az_account()
    data = existing.copy()
    data["subscription_id"] = subscription_id
    data["tenant_id"]       = tenant_id

    if choice in ["1", "8"]:
        tier = select_option("SKU tier:", list(SKU_OPTIONS.keys()), default="GeneralPurpose")
        data["pg_sku_name"] = select_option("SKU size:", SKU_OPTIONS[tier], default=existing.get("pg_sku_name"))

    if choice in ["2", "8"]:
        data["pg_storage_mb"] = select_option("Storage size:", STORAGE_OPTIONS, default=existing.get("pg_storage_mb", 32768))

    if choice in ["3", "8"]:
        print("\n  Backup retention days (7-35):")
        while True:
            val = input(f"  Enter value (default={existing.get('pg_backup_retention_days', 7)}): ").strip()
            if val == "":
                data["pg_backup_retention_days"] = existing.get("pg_backup_retention_days", 7)
                break
            if val.isdigit() and 7 <= int(val) <= 35:
                data["pg_backup_retention_days"] = int(val)
                break
            print_error("Enter a number between 7 and 35.")

    if choice in ["4", "8"]:
        data["pg_geo_redundant_backup_enabled"] = confirm("Enable geo-redundant backup?", default="n")

    if choice in ["5", "8"]:
        data["maintenance_day"] = DAYS_OF_WEEK.index(select_option("Maintenance day:", DAYS_OF_WEEK, default=DAYS_OF_WEEK[existing.get("maintenance_day", 0)]))
        print("\n  Maintenance start hour (0-23 UTC):")
        while True:
            val = input(f"  Enter value (default={existing.get('maintenance_hour', 2)}): ").strip()
            if val == "":
                data["maintenance_hour"] = existing.get("maintenance_hour", 2)
                break
            if val.isdigit() and 0 <= int(val) <= 23:
                data["maintenance_hour"] = int(val)
                break
            print_error("Enter a number between 0 and 23.")
        data["maintenance_minute"] = select_option("Maintenance start minute:", START_MINUTES, default=existing.get("maintenance_minute", 0))

    if choice in ["6", "8"]:
        data["pg_ha_enabled"] = confirm("Enable Zone-Redundant High Availability?", default="n")
        if data["pg_ha_enabled"]:
            available_zones = [z for z in ZONES if z != data.get("pg_zone", 1)]
            data["pg_ha_standby_zone"] = select_option("Standby zone:", available_zones, default=available_zones[0])

    if choice in ["7", "8"]:
        data["databases"] = collect_databases()

    print_summary(data)
    if not confirm("Proceed with these changes?", default="n"):
        print("\n  Cancelled.")
        return

    branch_name = f"modify/{name}"
    git_pull(repo_root)
    git_create_branch(repo_root, branch_name)

    write_tfvars(server_path / "terraform.tfvars", data)
    print_success("terraform.tfvars updated.")

    ok, _, err = run_command(
        f'git add . && git commit -m "Modify {name} PostgreSQL server"',
        cwd=repo_root
    )
    if not ok:
        print_error(f"Git commit failed: {err}")
        return

    git_push_branch(repo_root, branch_name)
    print_pr_instructions(repo_slug, branch_name, name, "modify")


def delete_server(repo_root, repo_slug):
    print_header("DELETE SERVER")

    servers = list_servers(repo_root)
    if not servers:
        print_error("No existing servers found.")
        return

    print("\n  Select server to delete:")
    options = [f"{env}/{name}" for env, name, _ in servers]
    selected = select_option("Available servers:", options)
    env, name = selected.split("/")
    server_path = repo_root / "environments" / env / name

    print(f"""
  ⚠  WARNING: You are about to delete {name}
  This will remove the server folder from the repo.
  After PR approval you must manually:
    1. Remove the Azure resource lock
    2. Run terraform destroy
    """)

    print("  Type the server name to confirm deletion:")
    confirm_name = input(f"  Server name: ").strip()
    if confirm_name != name:
        print_error(f"Name does not match. Expected: {name}")
        return

    if not confirm(f"Are you absolutely sure you want to delete {name}?", default="n"):
        print("\n  Cancelled.")
        return

    branch_name = f"delete/{name}"
    git_pull(repo_root)
    git_create_branch(repo_root, branch_name)

    import shutil
    shutil.rmtree(server_path)
    print_success(f"Removed folder: {server_path}")

    ok, _, err = run_command(
        f'git add . && git commit -m "Remove {name} PostgreSQL server"',
        cwd=repo_root
    )
    if not ok:
        print_error(f"Git commit failed: {err}")
        return

    git_push_branch(repo_root, branch_name)
    print_pr_instructions(repo_slug, branch_name, name, "delete")


# ===========================================================================
# MAIN MENU
# ===========================================================================

def main():
    print_header("PostgreSQL Flexible Server Manager")
    print("""
  This tool manages Azure PostgreSQL Flexible Server deployments
  via Terraform and GitHub Pull Request workflow.

  Prerequisites:
    - Authenticated to Azure  : az login
    - SSH access to GitHub    : ssh -T git@github.com
    """)

    repo_root  = get_repo_root()
    repo_slug  = get_github_remote(repo_root)

    print_success(f"Repo : {repo_slug}")
    print_success(f"Root : {repo_root}")

    while True:
        print("""
  Main Menu
  ---------
  1) Create a new server
  2) Modify an existing server
  3) Delete a server
  4) Exit
        """)
        choice = input("  Enter choice [1-4]: ").strip()
        if choice == "1":
            create_server(repo_root, repo_slug)
        elif choice == "2":
            modify_server(repo_root, repo_slug)
        elif choice == "3":
            delete_server(repo_root, repo_slug)
        elif choice == "4":
            print("\n  Goodbye.\n")
            sys.exit(0)
        else:
            print_error("Enter a number between 1 and 4.")


if __name__ == "__main__":
    main()
ENDOFFILE
