# Azure PaaS PostgreSQL Flexible Server - Terraform

Modular, repeatable Terraform project for deploying Azure Database for PostgreSQL Flexible Server with Private Endpoint connectivity. Each server instance is isolated in its own folder with its own remote state.

---

## Prerequisites

### 1. Install Azure CLI

    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
    az version

### 2. Install Terraform

    wget -O- https://apt.releases.hashicorp.com/gpg | \
      sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
      https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
      sudo tee /etc/apt/sources.list.d/hashicorp.list
    sudo apt update && sudo apt install -y terraform
    terraform version

### 3. Authenticate to Azure

    az login --tenant <your-tenant-id> --use-device-code
    az account set --subscription "<your-subscription-id>"
    az account show

### 4. Configure GitHub SSH

    ssh-keygen -t ed25519 -C "your@email.com"
    cat ~/.ssh/id_ed25519.pub
    # Copy output to GitHub > Settings > SSH Keys
    ssh -T git@github.com

### 5. Clone the Repo

    cd ~/Github-Personal
    git clone git@github.com:sivaraam73/azure-paas-test.git
    cd azure-paas-test

---

## Required Azure Infrastructure (Pre-existing)

The following must exist before deploying a PostgreSQL server.
These are managed by the networking team in a separate Terraform project.

    Resource Group          - Where the PostgreSQL server will be created
    Virtual Network         - Shared VNet
    Private Endpoint Subnet - Subnet for the PE NIC (no delegation needed)
    Private DNS Zone        - privatelink.postgres.database.azure.com linked to VNet
    State Storage Account   - Azure Blob for remote state

To create these for a sandbox/test environment:

    # Resource groups
    az group create --name rg-pgtest-dta --location malaysiawest
    az group create --name rg-network-dta --location malaysiawest
    az group create --name rg-terraform-state --location malaysiawest

    # State storage account (name must be globally unique)
    az storage account create \
      --name <unique-storage-name> \
      --resource-group rg-terraform-state \
      --location malaysiawest \
      --sku Standard_LRS \
      --kind StorageV2 \
      --allow-blob-public-access false

    az storage container create \
      --name tfstate \
      --account-name <unique-storage-name> \
      --auth-mode login

    # VNet and subnet
    az network vnet create \
      --name vnet-shared-dta \
      --resource-group rg-network-dta \
      --location malaysiawest \
      --address-prefix 10.10.0.0/16

    az network vnet subnet create \
      --name snet-private-endpoints \
      --resource-group rg-network-dta \
      --vnet-name vnet-shared-dta \
      --address-prefix 10.10.1.0/24

    # Private DNS zone and VNet link
    az network private-dns zone create \
      --name privatelink.postgres.database.azure.com \
      --resource-group rg-network-dta

    az network private-dns link vnet create \
      --name dns-link-vnet-shared-dta \
      --resource-group rg-network-dta \
      --zone-name privatelink.postgres.database.azure.com \
      --virtual-network vnet-shared-dta \
      --registration-enabled false

---

## Project Structure

    azure-paas-test/
    |-- modules/
    |   +-- postgresql/               # Shared module - never edit directly
    |       |-- main.tf
    |       |-- variables.tf
    |       |-- outputs.tf
    |       +-- versions.tf
    |
    |-- environments/
    |   |-- dta/
    |   |   +-- psql-myapp-dta-001/   # One folder per server instance
    |   |       |-- 00_global.tf       # Backend config - unique per server
    |   |       |-- main.tf            # Calls shared module - do not edit
    |   |       |-- variables.tf       # Variable declarations - do not edit
    |   |       |-- outputs.tf         # Outputs - do not edit
    |   |       +-- terraform.tfvars   # Engineer fills this in - gitignored
    |   +-- prod/
    |
    +-- _template/                    # Copy this for every new server
        |-- 00_global.tf
        |-- main.tf
        |-- variables.tf
        |-- outputs.tf
        +-- terraform.tfvars.example

---

## Creating a New Server

Step 1 - Copy the template

    cp -r _template environments/dta/psql-myapp-dta-001

Step 2 - Update the backend key

    nano environments/dta/psql-myapp-dta-001/00_global.tf

    Change:  key = "dta/psql-CHANGEME.tfstate"
    To:      key = "dta/psql-myapp-dta-001.tfstate"

Step 3 - Create and fill in tfvars

    cp environments/dta/psql-myapp-dta-001/terraform.tfvars.example \
       environments/dta/psql-myapp-dta-001/terraform.tfvars
    nano environments/dta/psql-myapp-dta-001/terraform.tfvars

Step 4 - Set the admin password (never put this in tfvars)

    export TF_VAR_pg_admin_password="YourSecureP@ssword123!"

Step 5 - Deploy

    cd environments/dta/psql-myapp-dta-001
    terraform init
    terraform plan -var-file="terraform.tfvars"
    terraform apply -var-file="terraform.tfvars"

Step 6 - Apply Azure resource lock

    az lock create \
      --name "lock-psql-myapp-dta-001" \
      --resource-group <your-rg> \
      --resource-type Microsoft.DBforPostgreSQL/flexibleServers \
      --resource "psql-myapp-dta-001" \
      --lock-type CanNotDelete \
      --notes "Protected. Remove manually before destroying."

Step 7 - Commit to GitHub

    cd ~/Github-Personal/azure-paas-test
    git add environments/dta/psql-myapp-dta-001/
    git commit -m "Add psql-myapp-dta-001 PostgreSQL server"
    git push origin main

---

## Modifying an Existing Server

    git pull origin main
    cd environments/dta/psql-myapp-dta-001
    nano terraform.tfvars
    export TF_VAR_pg_admin_password="YourSecureP@ssword123!"
    terraform plan -var-file="terraform.tfvars"
    terraform apply -var-file="terraform.tfvars"
    cd ~/Github-Personal/azure-paas-test
    git add environments/dta/psql-myapp-dta-001/terraform.tfvars
    git commit -m "Scale psql-myapp-dta-001 storage to 64GB"
    git push origin main

---

## Removing a Server

    # 1. Remove the Azure resource lock first
    az lock delete \
      --name "lock-psql-myapp-dta-001" \
      --resource-group <your-rg> \
      --resource-type Microsoft.DBforPostgreSQL/flexibleServers \
      --resource "psql-myapp-dta-001"

    # 2. Destroy
    export TF_VAR_pg_admin_password="YourSecureP@ssword123!"
    cd environments/dta/psql-myapp-dta-001
    terraform destroy -var-file="terraform.tfvars"

    # 3. Remove folder from repo
    cd ~/Github-Personal/azure-paas-test
    git rm -r environments/dta/psql-myapp-dta-001/
    git commit -m "Remove psql-myapp-dta-001"
    git push origin main

---

## SKU Reference

Burstable - dev/test only

    B_Standard_B1ms  =  1 vCPU,  2 GB RAM
    B_Standard_B2ms  =  2 vCPU,  8 GB RAM
    B_Standard_B4ms  =  4 vCPU, 16 GB RAM
    B_Standard_B8ms  =  8 vCPU, 32 GB RAM

General Purpose v5 - recommended for most workloads

    GP_Standard_D2ds_v5  =  2 vCPU,   8 GB RAM
    GP_Standard_D4ds_v5  =  4 vCPU,  16 GB RAM
    GP_Standard_D8ds_v5  =  8 vCPU,  32 GB RAM
    GP_Standard_D16ds_v5 = 16 vCPU,  64 GB RAM
    GP_Standard_D32ds_v5 = 32 vCPU, 128 GB RAM
    GP_Standard_D64ds_v5 = 64 vCPU, 256 GB RAM

Memory Optimized v5 - high memory workloads

    MO_Standard_E2ds_v5  =  2 vCPU,  16 GB RAM
    MO_Standard_E4ds_v5  =  4 vCPU,  32 GB RAM
    MO_Standard_E8ds_v5  =  8 vCPU,  64 GB RAM
    MO_Standard_E16ds_v5 = 16 vCPU, 128 GB RAM
    MO_Standard_E32ds_v5 = 32 vCPU, 256 GB RAM
    MO_Standard_E64ds_v5 = 64 vCPU, 512 GB RAM

---

## Storage Reference

    32768   =  32 GB
    65536   =  64 GB
    131072  = 128 GB
    262144  = 256 GB
    524288  = 512 GB
    1048576 =   1 TB
    2097152 =   2 TB
    4194304 =   4 TB

---

## Rules for Engineers

    1. Never edit main.tf, variables.tf, or outputs.tf inside the server folder
    2. Only edit 00_global.tf (once at creation) and terraform.tfvars
    3. Never commit terraform.tfvars - it is gitignored for a reason
    4. Always run terraform plan before apply and review carefully
    5. Always apply the Azure resource lock after creating a server
    6. Always remove the Azure resource lock before destroying a server
    7. Never run terraform destroy without first confirming with your team
