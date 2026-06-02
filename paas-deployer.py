#!/usr/bin/env python3
"""
paas-deployer.py — PostgreSQL Flexible Server Manager
Automates pre-flight checks, branch creation, tfvars generation, and GitHub PR workflow.
"""

import os
import re
import sys
import json
import shutil
import getpass
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

PG_VERSIONS   = [14, 15, 16, 17]
ZONES         = [1, 2, 3]
ENVIRONMENTS  = ["dta", "prod"]
DAYS_OF_WEEK  = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
START_MINUTES = [0, 30]
DNS_ZONE_NAME = "privatelink.postgres.database.azure.com"

# ===========================================================================
# DISPLAY HELPERS
# ===========================================================================

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def print_step(msg):
    print(f"\n  -> {msg}")

def print_success(msg):
    print(f"  [OK] {msg}")

def print_error(msg):
    print(f"  [ERROR] {msg}")

def print_missing(msg):
    print(f"  [MISSING] {msg}")

# ===========================================================================
# SHELL HELPER
# ===========================================================================

def run_command(cmd, cwd=None):
    result = subprocess.run(
        cmd, shell=True, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result.returncode == 0, result.stdout.strip(), result.stderr.strip()

# ===========================================================================
# INPUT HELPERS
# ===========================================================================

def validate_input(prompt, pattern, example, error_msg, default=None, min_len=1, max_len=100):
    default_hint = f" (default={default})" if default is not None else ""
    print(f"\n  {prompt}")
    print(f"  Format  : {error_msg}")
    print(f"  Example : {example}")
    while True:
        value = input(f"  Enter value{default_hint}: ").strip()
        if value == "" and default is not None:
            print_success(f"Using default: {default}")
            return str(default)
        if value == "":
            print_error("Cannot be empty.")
            continue
        if len(value) < min_len or len(value) > max_len:
            print_error(f"Length must be between {min_len} and {max_len} characters.")
            continue
        if not re.match(pattern, value):
            print_error(error_msg)
            continue
        print_success(f"Accepted: {value}")
        return value


def select_option(prompt, options, default=None):
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


def input_number(prompt, min_val, max_val, default):
    print(f"\n  {prompt} ({min_val}-{max_val}):")
    while True:
        val = input(f"  Enter value (default={default}): ").strip()
        if val == "":
            print_success(f"Using default: {default}")
            return default
        if val.isdigit() and min_val <= int(val) <= max_val:
            print_success(f"Accepted: {val}")
            return int(val)
        print_error(f"Enter a number between {min_val} and {max_val}.")


def collect_databases(existing=None):
    print("\n  Databases to create on this server.")
    print("  Press Enter with empty name when done.")
    print("  Format  : lowercase letters, numbers, hyphens or underscores")
    print("  Example : appdb")
    if existing:
        print(f"  Current : {', '.join(existing.keys())}")
    databases = {}
    while True:
        name = input("  Database name (or Enter to finish): ").strip()
        if name == "":
            if not databases:
                print_error("At least one database is required.")
                continue
            break
        if not re.match(r'^[a-z][a-z0-9_-]{1,62}$', name):
            print_error("Lowercase letters, numbers, hyphens or underscores. Min 2 chars.")
            continue
        databases[name] = {"name": name, "charset": "UTF8", "collation": "en_US.utf8"}
        print_success(f"Added: {name}")
    return databases


# ===========================================================================
# AZURE RESOURCE SELECTORS
# Show existing resources, let engineer pick or enter new name
# ===========================================================================

def _pick_or_new(label, items, new_label, validate_fn, default=None):
    """Generic picker: show existing items + option to create new."""
    options = items + [f"[ {new_label} ]"]
    print(f"\n  {label}:")
    if items:
        print(f"  Existing:")
    else:
        print(f"  None found.")
    for i, item in enumerate(options, 1):
        marker = " (default)" if item == default else ""
        print(f"    {i}) {item}{marker}")
    while True:
        choice = input(f"  Enter choice [1-{len(options)}]: ").strip()
        if choice == "" and default and default in items:
            print_success(f"Using default: {default}")
            return default
        if not choice.isdigit() or not (1 <= int(choice) <= len(options)):
            print_error(f"Enter a number between 1 and {len(options)}.")
            continue
        selected = options[int(choice) - 1]
        if selected == f"[ {new_label} ]":
            return validate_fn()
        print_success(f"Selected: {selected}")
        return selected


def select_resource_group(label, default=None):
    ok, out, _ = run_command('az group list --query "[].name" -o tsv')
    items = sorted(out.strip().split("\n")) if ok and out.strip() else []
    return _pick_or_new(
        label, items, "Enter new resource group name",
        lambda: validate_input(
            "New resource group name",
            r'^[a-zA-Z0-9._-]{1,90}$',
            "rg-network-dta",
            "Letters, numbers, hyphens, underscores and periods only.",
            min_len=1, max_len=90
        ),
        default=default
    )


def select_vnet(resource_group, default=None):
    ok, out, _ = run_command(
        f'az network vnet list --resource-group "{resource_group}" --query "[].name" -o tsv'
    )
    items = sorted(out.strip().split("\n")) if ok and out.strip() else []
    return _pick_or_new(
        f"VNet in {resource_group}", items, "Enter new VNet name",
        lambda: validate_input(
            "New VNet name",
            r'^[a-zA-Z0-9._-]{2,64}$',
            "vnet-shared-dta",
            "Letters, numbers, hyphens, underscores and periods only.",
            min_len=2, max_len=64
        ),
        default=default
    )


def select_subnet(vnet_name, resource_group, default=None):
    ok, out, _ = run_command(
        f'az network vnet subnet list --resource-group "{resource_group}" '
        f'--vnet-name "{vnet_name}" --query "[].name" -o tsv'
    )
    items = sorted(out.strip().split("\n")) if ok and out.strip() else []
    return _pick_or_new(
        f"Subnet in {vnet_name}", items, "Enter new subnet name",
        lambda: validate_input(
            "New subnet name",
            r'^[a-zA-Z0-9._-]{2,80}$',
            "snet-private-endpoints",
            "Letters, numbers, hyphens, underscores and periods only.",
            min_len=2, max_len=80
        ),
        default=default
    )


def select_location(label, default="malaysiawest"):
    ok, out, _ = run_command(
        'az account list-locations --query "[?metadata.regionCategory==\'Recommended\'].name" -o tsv'
    )
    items = sorted(out.strip().split("\n")) if ok and out.strip() else []
    return _pick_or_new(
        label, items, "Enter location name manually",
        lambda: validate_input(
            "Location name",
            r'^[a-z][a-z0-9]+$',
            "malaysiawest",
            "Lowercase letters and numbers only.",
            default=default, min_len=3, max_len=50
        ),
        default=default
    )


# ===========================================================================
# AZURE CLI HELPERS
# ===========================================================================

def get_az_account():
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


def get_rg_location(resource_group):
    ok, out, _ = run_command(f'az group show --name "{resource_group}" --query "location" -o tsv')
    return out.strip() if ok else None


def get_storage_account(repo_root):
    for env_dir in (repo_root / "environments").iterdir():
        if not env_dir.is_dir():
            continue
        for server_dir in env_dir.iterdir():
            tf = server_dir / "00_global.tf"
            if tf.exists():
                m = re.search(r'storage_account_name\s*=\s*"([^"]+)"', tf.read_text())
                if m:
                    return m.group(1)
    tf = repo_root / "_template" / "00_global.tf"
    if tf.exists():
        m = re.search(r'storage_account_name\s*=\s*"([^"]+)"', tf.read_text())
        if m:
            return m.group(1)
    return "stttfstatesiva001"


# ===========================================================================
# PRE-FLIGHT CHECKS — check and auto-create all dependencies
# ===========================================================================

def check_and_create_resource_group(name):
    print(f"  Checking Resource Group     : {name}")
    ok, _, _ = run_command(f'az group show --name "{name}" --output none 2>/dev/null')
    if ok:
        print_success(f"Resource Group exists       : {name}")
        return True
    print_missing(f"Resource Group              : {name}")
    location = select_location(f"Location for new resource group '{name}'")
    print_step(f"Creating Resource Group: {name}...")
    ok, _, err = run_command(f'az group create --name "{name}" --location "{location}" --output none')
    if not ok:
        print_error(f"Failed: {err}")
        return False
    print_success(f"Resource Group created      : {name}")
    return True


def check_and_create_vnet(vnet_name, resource_group):
    print(f"  Checking VNet               : {vnet_name}")
    ok, _, _ = run_command(
        f'az network vnet show --name "{vnet_name}" --resource-group "{resource_group}" --output none 2>/dev/null'
    )
    if ok:
        print_success(f"VNet exists                 : {vnet_name}")
        return True
    print_missing(f"VNet                        : {vnet_name}")
    location = get_rg_location(resource_group) or "malaysiawest"
    address_prefix = validate_input(
        "VNet address prefix",
        r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$',
        "10.10.0.0/16",
        "Valid CIDR format e.g. 10.10.0.0/16",
        default="10.10.0.0/16"
    )
    print_step(f"Creating VNet: {vnet_name}...")
    ok, _, err = run_command(
        f'az network vnet create --name "{vnet_name}" --resource-group "{resource_group}" '
        f'--location "{location}" --address-prefix "{address_prefix}" --output none'
    )
    if not ok:
        print_error(f"Failed: {err}")
        return False
    print_success(f"VNet created                : {vnet_name}")
    return True


def check_and_create_subnet(subnet_name, vnet_name, resource_group):
    print(f"  Checking Subnet             : {subnet_name}")
    ok, _, _ = run_command(
        f'az network vnet subnet show --name "{subnet_name}" '
        f'--vnet-name "{vnet_name}" --resource-group "{resource_group}" --output none 2>/dev/null'
    )
    if ok:
        print_success(f"Subnet exists               : {subnet_name}")
        return True
    print_missing(f"Subnet                      : {subnet_name}")
    address_prefix = validate_input(
        "Subnet address prefix",
        r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$',
        "10.10.1.0/24",
        "Valid CIDR format e.g. 10.10.1.0/24",
        default="10.10.1.0/24"
    )
    print_step(f"Creating Subnet: {subnet_name}...")
    ok, _, err = run_command(
        f'az network vnet subnet create --name "{subnet_name}" '
        f'--vnet-name "{vnet_name}" --resource-group "{resource_group}" '
        f'--address-prefix "{address_prefix}" --output none'
    )
    if not ok:
        print_error(f"Failed: {err}")
        return False
    print_success(f"Subnet created              : {subnet_name}")
    return True


def check_and_create_dns_zone(zone_name, resource_group):
    print(f"  Checking Private DNS Zone   : {zone_name}")
    ok, _, _ = run_command(
        f'az network private-dns zone show --name "{zone_name}" '
        f'--resource-group "{resource_group}" --output none 2>/dev/null'
    )
    if ok:
        print_success(f"Private DNS Zone exists     : {zone_name}")
        return True
    print_missing(f"Private DNS Zone            : {zone_name}")
    print_step(f"Creating Private DNS Zone: {zone_name}...")
    ok, _, err = run_command(
        f'az network private-dns zone create --name "{zone_name}" '
        f'--resource-group "{resource_group}" --output none'
    )
    if not ok:
        print_error(f"Failed: {err}")
        return False
    print_success(f"Private DNS Zone created    : {zone_name}")
    return True


def check_and_create_dns_link(zone_name, zone_rg, vnet_name, vnet_rg):
    print(f"  Checking DNS VNet Link      : {zone_name} -> {vnet_name}")
    # Get VNet resource ID
    ok, vnet_id, _ = run_command(
        f'az network vnet show --name "{vnet_name}" '
        f'--resource-group "{vnet_rg}" --query "id" -o tsv'
    )
    if not ok:
        print_error("Could not get VNet resource ID.")
        return False
    vnet_id = vnet_id.strip().lower()
    # List all links and check if any already link to this VNet
    ok, out, _ = run_command(
        f'az network private-dns link vnet list '
        f'--resource-group "{zone_rg}" '
        f'--zone-name "{zone_name}" '
        f'--output json'
    )
    if ok and out.strip():
        try:
            links = json.loads(out)
            for link in links:
                linked_vnet = link.get("virtualNetwork", {}).get("id", "").lower()
                if linked_vnet == vnet_id:
                    print_success(f"DNS VNet Link exists        : {link.get('name')}")
                    return True
        except Exception:
            pass
    link_name = f"dns-link-{vnet_name}"
    print_missing(f"DNS VNet Link               : {link_name}")
    print_step(f"Creating DNS VNet Link: {link_name}...")
    ok, _, err = run_command(
        f'az network private-dns link vnet create '
        f'--name "{link_name}" '
        f'--resource-group "{zone_rg}" '
        f'--zone-name "{zone_name}" '
        f'--virtual-network "{vnet_id}" '
        f'--registration-enabled false '
        f'--output none'
    )
    if not ok:
        print_error(f"Failed: {err}")
        return False
    print_success(f"DNS VNet Link created       : {link_name}")
    return True


def run_preflight_checks(data):
    print_header("PRE-FLIGHT DEPENDENCY CHECKS")
    rgs = list(dict.fromkeys([
        data["pg_resource_group_name"],
        data["vnet_resource_group_name"],
        data["private_dns_zone_resource_group_name"],
    ]))
    for rg in rgs:
        if not check_and_create_resource_group(rg):
            return False
    if not check_and_create_vnet(data["vnet_name"], data["vnet_resource_group_name"]):
        return False
    if not check_and_create_subnet(data["pe_subnet_name"], data["vnet_name"], data["vnet_resource_group_name"]):
        return False
    if not check_and_create_dns_zone(DNS_ZONE_NAME, data["private_dns_zone_resource_group_name"]):
        return False
    if not check_and_create_dns_link(
        DNS_ZONE_NAME,
        data["private_dns_zone_resource_group_name"],
        data["vnet_name"],
        data["vnet_resource_group_name"]
    ):
        return False
    print_success("All dependencies are ready.")
    return True


# ===========================================================================
# POST-MERGE DEPLOY
# ===========================================================================

def post_merge_deploy(repo_root, server_name, environment, action):
    if action == "delete":
        print("\n  After PR is merged, remember to:")
        print(f"    1. Remove the Azure resource lock for {server_name}")
        print(f"    2. cd environments/{environment}/{server_name}")
        print(f"    3. export TF_VAR_pg_admin_password='YourPassword'")
        print(f"    4. terraform destroy -var-file=\"terraform.tfvars\"")
        return

    if not confirm("Have you merged the PR?", default="n"):
        print("\n  Run terraform manually when ready:")
        print(f"    cd environments/{environment}/{server_name}")
        print(f"    export TF_VAR_pg_admin_password='YourPassword'")
        if action == "create":
            print(f"    terraform init")
        print(f"    terraform apply -var-file=\"terraform.tfvars\"")
        return

    print_step("Pulling merged changes from main...")
    ok, _, err = run_command("git checkout main", cwd=repo_root)
    if not ok:
        print_error(f"Failed to checkout main: {err}")
        return
    ok, _, err = run_command("git pull origin main", cwd=repo_root)
    if not ok:
        print_error(f"Failed to pull: {err}")
        return
    print_success("Up to date with main.")

    server_path = repo_root / "environments" / environment / server_name
    print("\n  Admin password is required for Terraform.")
    print("  This will NOT be stored anywhere.")
    password = getpass.getpass("  Enter pg_admin_password: ")
    env = os.environ.copy()
    env["TF_VAR_pg_admin_password"] = password

    if action == "create":
        print_step("Running terraform init...")
        result = subprocess.run("terraform init", shell=True, cwd=server_path, env=env)
        if result.returncode != 0:
            print_error("terraform init failed.")
            return

    print_step("Running terraform plan...")
    result = subprocess.run(
        'terraform plan -var-file="terraform.tfvars"',
        shell=True, cwd=server_path, env=env
    )
    if result.returncode != 0:
        print_error("terraform plan failed.")
        return

    if not confirm("Plan looks good. Apply now?", default="n"):
        print("\n  Apply cancelled. Run manually when ready:")
        print(f"    cd environments/{environment}/{server_name}")
        print(f"    terraform apply -var-file=\"terraform.tfvars\"")
        return

    print_step("Running terraform apply...")
    result = subprocess.run(
        'terraform apply -var-file="terraform.tfvars"',
        shell=True, cwd=server_path, env=env
    )
    if result.returncode != 0:
        print_error("terraform apply failed.")
        return

    print_success("Deployment complete!")
    if action == "create":
        print("\n  Don't forget to add the Azure resource lock:")
        print(f"    az lock create \\")
        print(f"      --name lock-{server_name} \\")
        print(f"      --resource-group <your-rg> \\")
        print(f"      --resource-type Microsoft.DBforPostgreSQL/flexibleServers \\")
        print(f"      --resource {server_name} \\")
        print(f"      --lock-type CanNotDelete")


# ===========================================================================
# GIT HELPERS
# ===========================================================================

def get_repo_root():
    root = Path(__file__).parent.resolve()
    if not (root / "environments").exists() or not (root / "_template").exists():
        print_error("Could not find environments/ and _template/ in the same folder as paas-deployer.py.")
        sys.exit(1)
    return root


def get_github_remote(repo_root):
    ok, out, _ = run_command("git remote get-url origin", cwd=repo_root)
    if not ok or not out:
        print_error("Could not determine GitHub remote URL.")
        sys.exit(1)
    match = re.search(r'[:/]([^:/]+/[^/]+?)(?:\.git)?$', out)
    if not match:
        print_error(f"Could not parse remote URL: {out}")
        sys.exit(1)
    return match.group(1)


def git_pull(repo_root):
    print_step("Switching to main and pulling latest...")
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
    run_command(f"git branch -D {branch_name}", cwd=repo_root)
    ok, _, err = run_command(f"git checkout -b {branch_name}", cwd=repo_root)
    if not ok:
        print_error(f"Failed to create branch: {err}")
        sys.exit(1)
    print_success(f"Branch created: {branch_name}")


def git_commit_and_push(repo_root, branch_name, message):
    print_step("Committing changes...")
    run_command("git add .", cwd=repo_root)
    ok, _, err = run_command(f'git commit -m "{message}"', cwd=repo_root)
    if not ok:
        print_error(f"Git commit failed: {err}")
        sys.exit(1)
    print_success("Changes committed.")
    print_step(f"Pushing branch: {branch_name}")
    ok, _, err = run_command(f"git push origin {branch_name}", cwd=repo_root)
    if not ok:
        print_error(f"Failed to push: {err}")
        sys.exit(1)
    print_success("Branch pushed.")


def print_next_steps(repo_slug, branch_name, server_name, environment, action):
    pr_url = f"https://github.com/{repo_slug}/pull/new/{branch_name}"
    print("\n" + "=" * 60)
    print("  NEXT STEPS")
    print("=" * 60)
    print(f"\n  1. Create Pull Request:")
    print(f"     {pr_url}")
    print(f"\n  2. Get PR reviewed and approved.")
    if action == "create":
        print(f"\n  3. After merge, deploy:")
        print(f"     cd environments/{environment}/{server_name}")
        print(f"     export TF_VAR_pg_admin_password='YourSecureP@ssword123!'")
        print(f"     terraform init")
        print(f"     terraform apply -var-file=\"terraform.tfvars\"")
        print(f"\n  4. After apply, add resource lock:")
        print(f"     az lock create \\")
        print(f"       --name lock-{server_name} \\")
        print(f"       --resource-group <your-rg> \\")
        print(f"       --resource-type Microsoft.DBforPostgreSQL/flexibleServers \\")
        print(f"       --resource {server_name} \\")
        print(f"       --lock-type CanNotDelete")
    elif action == "modify":
        print(f"\n  3. After merge, apply changes:")
        print(f"     cd environments/{environment}/{server_name}")
        print(f"     export TF_VAR_pg_admin_password='YourSecureP@ssword123!'")
        print(f"     terraform apply -var-file=\"terraform.tfvars\"")
    elif action == "delete":
        print(f"\n  3. After merge, remove lock then destroy:")
        print(f"     az lock delete \\")
        print(f"       --name lock-{server_name} \\")
        print(f"       --resource-group <your-rg> \\")
        print(f"       --resource-type Microsoft.DBforPostgreSQL/flexibleServers \\")
        print(f"       --resource {server_name}")
        print(f"     cd environments/{environment}/{server_name}")
        print(f"     export TF_VAR_pg_admin_password='YourSecureP@ssword123!'")
        print(f"     terraform destroy -var-file=\"terraform.tfvars\"")
    print()


# ===========================================================================
# FILE WRITERS
# ===========================================================================

def write_global_tf(path, environment, server_name, storage_account):
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


def write_main_tf(path):
    content = """# ===========================================================================
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
"""
    with open(path, "w") as f:
        f.write(content)


def write_variables_tf(path):
    content = """# ===========================================================================
# This file is identical across all server instances — do not edit.
# ===========================================================================

variable "subscription_id" { type = string; sensitive = true }
variable "tenant_id"       { type = string; sensitive = true }
variable "environment"     { type = string }
variable "project"         { type = string }

variable "pg_resource_group_name"               { type = string }
variable "vnet_name"                            { type = string }
variable "vnet_resource_group_name"             { type = string }
variable "pe_subnet_name"                       { type = string }
variable "private_dns_zone_name"                { type = string; default = "privatelink.postgres.database.azure.com" }
variable "private_dns_zone_resource_group_name" { type = string }

variable "pg_server_name"       { type = string }
variable "pg_version"           { type = number; default = 16 }
variable "pg_sku_name"          { type = string; default = "GP_Standard_D2ds_v5" }
variable "pg_storage_mb"        { type = number; default = 32768 }
variable "pg_storage_tier"      { type = string; default = null }
variable "pg_zone"              { type = number; default = 1 }
variable "pg_auto_grow_enabled" { type = bool;   default = false }

variable "pg_admin_login"    { type = string; default = "psqladmin" }
variable "pg_admin_password" { type = string; sensitive = true }

variable "pg_backup_retention_days"        { type = number; default = 7 }
variable "pg_geo_redundant_backup_enabled" { type = bool;   default = false }

variable "pg_maintenance_window" {
  type = object({
    day_of_week  = number
    start_hour   = number
    start_minute = number
  })
  default = { day_of_week = 0; start_hour = 2; start_minute = 0 }
}

variable "pg_ha_enabled"      { type = bool;   default = false }
variable "pg_ha_standby_zone" { type = number; default = 2 }

variable "pg_databases" {
  type = map(object({
    name      = string
    charset   = optional(string, "UTF8")
    collation = optional(string, "en_US.utf8")
  }))
  default = {}
}
"""
    with open(path, "w") as f:
        f.write(content)


def write_outputs_tf(path):
    content = """# ===========================================================================
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
"""
    with open(path, "w") as f:
        f.write(content)


def write_tfvars(path, data):
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
# Generated by paas-deployer.py — do not edit manually
# ===========================================================================

subscription_id = "{data["subscription_id"]}"
tenant_id       = "{data["tenant_id"]}"
environment     = "{data["environment"]}"
project         = "{data["project"]}"

pg_resource_group_name = "{data["pg_resource_group_name"]}"

vnet_name                            = "{data["vnet_name"]}"
vnet_resource_group_name             = "{data["vnet_resource_group_name"]}"
pe_subnet_name                       = "{data["pe_subnet_name"]}"
private_dns_zone_name                = "privatelink.postgres.database.azure.com"
private_dns_zone_resource_group_name = "{data["private_dns_zone_resource_group_name"]}"

pg_server_name       = "{data["server_name"]}"
pg_version           = {data["pg_version"]}
pg_sku_name          = "{data["pg_sku_name"]}"
pg_storage_mb        = {data["pg_storage_mb"]}
pg_storage_tier      = null
pg_auto_grow_enabled = {str(data["pg_auto_grow_enabled"]).lower()}
pg_zone              = {data["pg_zone"]}

pg_admin_login = "{data["pg_admin_login"]}"

pg_backup_retention_days        = {data["pg_backup_retention_days"]}
pg_geo_redundant_backup_enabled = {str(data["pg_geo_redundant_backup_enabled"]).lower()}

pg_maintenance_window = {{
  day_of_week  = {data["maintenance_day"]}
  start_hour   = {data["maintenance_hour"]}
  start_minute = {data["maintenance_minute"]}
}}

pg_ha_enabled      = {str(data["pg_ha_enabled"]).lower()}
pg_ha_standby_zone = {data["pg_ha_standby_zone"]}

pg_databases = {{
{db_block}}}
"""
    with open(path, "w") as f:
        f.write(content)


# ===========================================================================
# READ EXISTING TFVARS
# ===========================================================================

def read_existing_tfvars(tfvars_path):
    data = {}
    if not tfvars_path.exists():
        return data
    content = tfvars_path.read_text()

    def extract(key, cast=str):
        match = re.search(rf'^{key}\s*=\s*"?([^"\n#]+)"?', content, re.MULTILINE)
        if match:
            val = match.group(1).strip().strip('"')
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
    data["pg_ha_standby_zone"]                   = extract("pg_ha_standby_zone", int)

    for bool_key, tf_key in [
        ("pg_auto_grow_enabled",            "pg_auto_grow_enabled"),
        ("pg_geo_redundant_backup_enabled", "pg_geo_redundant_backup_enabled"),
        ("pg_ha_enabled",                   "pg_ha_enabled"),
    ]:
        m = re.search(rf'^{tf_key}\s*=\s*(true|false)', content, re.MULTILINE)
        if m:
            data[bool_key] = m.group(1) == "true"

    db_names = re.findall(r'^\s*name\s*=\s*"([^"]+)"', content, re.MULTILINE)
    data["databases"] = {
        name: {"name": name, "charset": "UTF8", "collation": "en_US.utf8"}
        for name in db_names
    }
    return data


def list_servers(repo_root):
    servers = []
    env_path = repo_root / "environments"
    for env_dir in sorted(env_path.iterdir()):
        if not env_dir.is_dir():
            continue
        for server_dir in sorted(env_dir.iterdir()):
            if server_dir.is_dir() and (server_dir / "terraform.tfvars").exists():
                servers.append((env_dir.name, server_dir.name, server_dir))
    return servers


# ===========================================================================
# INPUT COLLECTION
# ===========================================================================

def collect_inputs(subscription_id, tenant_id, existing=None):
    e = existing or {}
    data = {}
    data["subscription_id"] = subscription_id
    data["tenant_id"]       = tenant_id

    print_header("Environment")
    data["environment"] = select_option(
        "Select environment:", ENVIRONMENTS, default=e.get("environment", "dta")
    )

    print_header("Project Details")
    data["project"] = validate_input(
        "Project name",
        r'^[a-z][a-z0-9-]{1,18}[a-z0-9]$',
        "myapp",
        "Lowercase letters, numbers and hyphens only. 3-20 chars.",
        default=e.get("project"), min_len=3, max_len=20
    )
    data["server_name"] = validate_input(
        "Server name (must be globally unique across all of Azure)",
        r'^[a-z][a-z0-9-]{1,61}[a-z0-9]$',
        f"psql-myapp-{data.get('environment','dta')}-001",
        "Lowercase letters, numbers and hyphens only. 3-63 chars.",
        default=e.get("server_name"), min_len=3, max_len=63
    )

    print_header("Resource Group for PostgreSQL Server")
    data["pg_resource_group_name"] = select_resource_group(
        "PostgreSQL server resource group (select existing or create new)",
        default=e.get("pg_resource_group_name")
    )

    print_header("Networking")
    data["vnet_resource_group_name"] = select_resource_group(
        "VNet resource group (select existing or create new)",
        default=e.get("vnet_resource_group_name")
    )
    data["vnet_name"] = select_vnet(
        data["vnet_resource_group_name"],
        default=e.get("vnet_name")
    )
    data["pe_subnet_name"] = select_subnet(
        data["vnet_name"],
        data["vnet_resource_group_name"],
        default=e.get("pe_subnet_name")
    )
    data["private_dns_zone_resource_group_name"] = select_resource_group(
        "Private DNS zone resource group (select existing or create new)",
        default=e.get("private_dns_zone_resource_group_name")
    )
    data["private_dns_zone_name"] = DNS_ZONE_NAME

    print_header("PostgreSQL Server")
    data["pg_version"] = select_option(
        "PostgreSQL version:", PG_VERSIONS, default=e.get("pg_version", 16)
    )
    tier = select_option(
        "SKU tier:", list(SKU_OPTIONS.keys()), default="GeneralPurpose"
    )
    data["pg_sku_name"] = select_option(
        "SKU size:", SKU_OPTIONS[tier], default=e.get("pg_sku_name")
    )
    data["pg_storage_mb"] = select_option(
        "Storage size:", STORAGE_OPTIONS, default=e.get("pg_storage_mb", 32768)
    )
    data["pg_zone"] = select_option(
        "Availability zone:", ZONES, default=e.get("pg_zone", 1)
    )
    data["pg_auto_grow_enabled"] = confirm(
        "Enable storage auto-grow? (recommended for prod)", default="n"
    )

    print_header("Administrator")
    data["pg_admin_login"] = validate_input(
        "Admin login username",
        r'^[a-zA-Z][a-zA-Z0-9_]{1,62}$',
        "psqladmin",
        "Letters, numbers and underscores. Must start with a letter. 2-63 chars.",
        default=e.get("pg_admin_login", "psqladmin"), min_len=2, max_len=63
    )

    print_header("Backup")
    data["pg_backup_retention_days"] = input_number(
        "Backup retention days", 7, 35, default=e.get("pg_backup_retention_days", 7)
    )
    data["pg_geo_redundant_backup_enabled"] = confirm(
        "Enable geo-redundant backup? (recommended for prod)", default="n"
    )

    print_header("Maintenance Window")
    day_name = select_option(
        "Maintenance day:", DAYS_OF_WEEK,
        default=DAYS_OF_WEEK[e.get("maintenance_day", 0)]
    )
    data["maintenance_day"]    = DAYS_OF_WEEK.index(day_name)
    data["maintenance_hour"]   = input_number(
        "Maintenance start hour (UTC)", 0, 23, default=e.get("maintenance_hour", 2)
    )
    data["maintenance_minute"] = select_option(
        "Maintenance start minute:", START_MINUTES, default=e.get("maintenance_minute", 0)
    )

    print_header("High Availability")
    data["pg_ha_enabled"] = confirm(
        "Enable Zone-Redundant High Availability? (recommended for prod)", default="n"
    )
    if data["pg_ha_enabled"]:
        available_zones = [z for z in ZONES if z != data["pg_zone"]]
        data["pg_ha_standby_zone"] = select_option(
            "Standby availability zone:", available_zones, default=available_zones[0]
        )
    else:
        data["pg_ha_standby_zone"] = 2 if data["pg_zone"] != 2 else 3

    print_header("Databases")
    data["databases"] = collect_databases(existing=e.get("databases"))

    return data


def print_summary(data):
    print_header("SUMMARY — Please review before proceeding")
    print(f"""
  Environment     : {data['environment']}
  Project         : {data['project']}
  Server name     : {data['server_name']}

  Resource Group  : {data['pg_resource_group_name']}
  VNet RG         : {data['vnet_resource_group_name']}
  VNet            : {data['vnet_name']}
  PE Subnet       : {data['pe_subnet_name']}
  DNS Zone RG     : {data['private_dns_zone_resource_group_name']}
  DNS Zone        : {data['private_dns_zone_name']}

  PG Version      : {data['pg_version']}
  SKU             : {data['pg_sku_name']}
  Storage         : {data['pg_storage_mb']} MB
  Zone            : {data['pg_zone']}
  Auto Grow       : {data['pg_auto_grow_enabled']}
  Admin Login     : {data['pg_admin_login']}

  Backup Days     : {data['pg_backup_retention_days']}
  Geo Redundant   : {data['pg_geo_redundant_backup_enabled']}

  Maintenance     : {DAYS_OF_WEEK[data['maintenance_day']]} {data['maintenance_hour']:02d}:{data['maintenance_minute']:02d} UTC

  HA Enabled      : {data['pg_ha_enabled']}
  HA Standby Zone : {data['pg_ha_standby_zone']}

  Databases       : {', '.join(data['databases'].keys())}

  Subscription ID : {data['subscription_id']}
  Tenant ID       : {data['tenant_id']}
    """)


# ===========================================================================
# FLOWS
# ===========================================================================

def create_server(repo_root, repo_slug):
    clear_screen()
    print_header("CREATE NEW SERVER")
    subscription_id, tenant_id = get_az_account()
    storage_account = get_storage_account(repo_root)

    data = collect_inputs(subscription_id, tenant_id)
    print_summary(data)

    if not confirm("Proceed with these settings?", default="n"):
        print("\n  Cancelled.")
        return

    if not run_preflight_checks(data):
        print_error("Pre-flight checks failed. Please resolve the issues and try again.")
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

    print_step("Creating server folder...")
    server_path.mkdir(parents=True, exist_ok=True)
    write_global_tf(server_path / "00_global.tf", environment, server_name, storage_account)
    write_main_tf(server_path / "main.tf")
    write_variables_tf(server_path / "variables.tf")
    write_outputs_tf(server_path / "outputs.tf")
    write_tfvars(server_path / "terraform.tfvars", data)
    print_success(f"Server folder created: environments/{environment}/{server_name}")

    git_commit_and_push(repo_root, branch_name, f"Add {server_name} PostgreSQL server")
    print_next_steps(repo_slug, branch_name, server_name, environment, "create")
    post_merge_deploy(repo_root, server_name, environment, "create")


def modify_server(repo_root, repo_slug):
    clear_screen()
    print_header("MODIFY EXISTING SERVER")

    servers = list_servers(repo_root)
    if not servers:
        print_error("No existing servers found.")
        return

    options = [f"{env}/{name}" for env, name, _ in servers]
    selected = select_option("Select server to modify:", options)
    env, name = selected.split("/")
    server_path = repo_root / "environments" / env / name

    print_step("Reading current configuration...")
    existing = read_existing_tfvars(server_path / "terraform.tfvars")

    print_header("WHAT WOULD YOU LIKE TO MODIFY?")
    print("""
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
        print_header("SKU")
        tier = select_option("SKU tier:", list(SKU_OPTIONS.keys()), default="GeneralPurpose")
        data["pg_sku_name"] = select_option("SKU size:", SKU_OPTIONS[tier], default=existing.get("pg_sku_name"))

    if choice in ["2", "8"]:
        print_header("Storage")
        data["pg_storage_mb"] = select_option("Storage size:", STORAGE_OPTIONS, default=existing.get("pg_storage_mb", 32768))

    if choice in ["3", "8"]:
        print_header("Backup Retention")
        data["pg_backup_retention_days"] = input_number("Backup retention days", 7, 35, default=existing.get("pg_backup_retention_days", 7))

    if choice in ["4", "8"]:
        print_header("Geo Redundant Backup")
        data["pg_geo_redundant_backup_enabled"] = confirm("Enable geo-redundant backup?", default="n")

    if choice in ["5", "8"]:
        print_header("Maintenance Window")
        day_name = select_option("Maintenance day:", DAYS_OF_WEEK, default=DAYS_OF_WEEK[existing.get("maintenance_day", 0)])
        data["maintenance_day"]    = DAYS_OF_WEEK.index(day_name)
        data["maintenance_hour"]   = input_number("Maintenance start hour (UTC)", 0, 23, default=existing.get("maintenance_hour", 2))
        data["maintenance_minute"] = select_option("Maintenance start minute:", START_MINUTES, default=existing.get("maintenance_minute", 0))

    if choice in ["6", "8"]:
        print_header("High Availability")
        data["pg_ha_enabled"] = confirm("Enable Zone-Redundant High Availability?", default="n")
        if data["pg_ha_enabled"]:
            available_zones = [z for z in ZONES if z != data.get("pg_zone", 1)]
            data["pg_ha_standby_zone"] = select_option("Standby zone:", available_zones, default=available_zones[0])

    if choice in ["7", "8"]:
        print_header("Databases")
        data["databases"] = collect_databases(existing=existing.get("databases"))

    print_summary(data)
    if not confirm("Proceed with these changes?", default="n"):
        print("\n  Cancelled.")
        return

    branch_name = f"modify/{name}"
    git_pull(repo_root)
    git_create_branch(repo_root, branch_name)

    write_tfvars(server_path / "terraform.tfvars", data)
    print_success("terraform.tfvars updated.")

    git_commit_and_push(repo_root, branch_name, f"Modify {name} PostgreSQL server")
    print_next_steps(repo_slug, branch_name, name, env, "modify")
    post_merge_deploy(repo_root, name, env, "modify")


def delete_server(repo_root, repo_slug):
    clear_screen()
    print_header("DELETE SERVER")

    servers = list_servers(repo_root)
    if not servers:
        print_error("No existing servers found.")
        return

    options = [f"{env}/{name}" for env, name, _ in servers]
    selected = select_option("Select server to delete:", options)
    env, name = selected.split("/")
    server_path = repo_root / "environments" / env / name

    print(f"""
  WARNING: You are about to delete {name}
  This removes the server folder from the repo.
  After PR approval you must manually:
    1. Remove the Azure resource lock
    2. Run terraform destroy
    """)

    print("  To confirm, type the server name exactly:")
    confirm_name = input("  Server name: ").strip()
    if confirm_name != name:
        print_error(f"Name does not match. Expected: {name}")
        return

    if not confirm(f"Are you absolutely sure you want to delete {name}?", default="n"):
        print("\n  Cancelled.")
        return

    branch_name = f"delete/{name}"
    git_pull(repo_root)
    git_create_branch(repo_root, branch_name)

    shutil.rmtree(server_path)
    print_success(f"Removed: environments/{env}/{name}")

    git_commit_and_push(repo_root, branch_name, f"Remove {name} PostgreSQL server")
    print_next_steps(repo_slug, branch_name, name, env, "delete")
    post_merge_deploy(repo_root, name, env, "delete")


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    clear_screen()
    print_header("paas-deployer — PostgreSQL Flexible Server Manager")
    print("""
  Manages Azure PostgreSQL Flexible Server deployments
  via Terraform and GitHub Pull Request workflow.

  Prerequisites:
    - Logged in to Azure  : az login --tenant <id> --use-device-code
    - SSH access to GitHub: ssh -T git@github.com
    """)

    repo_root = get_repo_root()
    repo_slug = get_github_remote(repo_root)

    print_success(f"Terraform repo : {repo_root}")
    print_success(f"GitHub remote  : {repo_slug}")

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
            input("\n  Press Enter to return to main menu...")
            clear_screen()
        elif choice == "2":
            modify_server(repo_root, repo_slug)
            input("\n  Press Enter to return to main menu...")
            clear_screen()
        elif choice == "3":
            delete_server(repo_root, repo_slug)
            input("\n  Press Enter to return to main menu...")
            clear_screen()
        elif choice == "4":
            print("\n  Goodbye.\n")
            sys.exit(0)
        else:
            print_error("Enter a number between 1 and 4.")


if __name__ == "__main__":
    main()
