<#
.SYNOPSIS
Grants the GPT and Kimi agents read access to evaluation images.

.DESCRIPTION
Uses each deployed agent's runtime identity to assign Storage Blob Data Reader
at the eval-images container scope, not across the entire storage account.

.NOTES
Run from the workspace root with Azure CLI and azd installed and authenticated.
Select the subscription containing your storage account before running this script.
Supply its name with -StorageAccountName.
The caller must have permission to create role assignments at the target scope.
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]{3,24}$')]
    [string]$StorageAccountName
)

# Resolve the storage account in the selected subscription; stop if it is unavailable.
$storageId = az storage account list `
    --query "[?name=='$StorageAccountName'].id | [0]" --output tsv
if ($LASTEXITCODE -ne 0 -or -not $storageId) { throw "Cannot find $StorageAccountName in the selected subscription." }
# Restrict blob access to the evaluation image container.
$scope = "$storageId/blobServices/default/containers/eval-images"

foreach ($name in @("store-image-inspector-gpt", "store-image-inspector-kimi")) {
    # Query the deployed instance rather than inferring its identity from the agent name.
    $raw = azd -C .\deployments\ncus --environment ncus-demo `
        ai agent show $name --output json
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect runtime identity for $name." }
    $deployed = $raw | ConvertFrom-Json
    $principalId = $deployed.instance_identity.principal_id
    if (-not $principalId) { throw "No instance_identity.principal_id for $name; do not guess a principal." }
    # Use the runtime principal's object ID to grant read-only blob data access.
    az role assignment create --assignee-object-id $principalId `
        --assignee-principal-type ServicePrincipal `
        --role "Storage Blob Data Reader" --scope $scope
    if ($LASTEXITCODE -ne 0) { throw "Blob role assignment failed for $name." }
}