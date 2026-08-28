param(
    [Parameter(Mandatory = $true)][string]$Candidate,
    [Parameter(Mandatory = $true)][string]$Destination,
    [string]$ExpectedPackId = "9045db86cf29d54f526a918be95c74cc37db87597bcc443cfbdb6f396ca04ef1",
    [int]$ExpectedRecords = 104978
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Candidate -PathType Container)) {
    throw "Candidate does not exist: $Candidate"
}
$manifest = Get-ChildItem -LiteralPath $Candidate -Recurse -File -Filter "manifest.json" | Select-Object -First 1
if ($null -eq $manifest) { throw "Pack manifest.json not found" }
$manifestData = Get-Content -LiteralPath $manifest.FullName -Raw | ConvertFrom-Json
if ($manifestData.pack_id -ne $ExpectedPackId) { throw "Knowledge Pack identity mismatch" }
$manifestRecords = @($manifestData.record_inventory).Count
if ($manifestRecords -ne $ExpectedRecords) { throw "Knowledge Pack manifest record count mismatch" }

$destinationPath = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $destinationPath) { throw "Destination must be new: $destinationPath" }
New-Item -ItemType Directory -Path $destinationPath | Out-Null
Get-ChildItem -LiteralPath $Candidate -Force | Copy-Item -Destination $destinationPath -Recurse

$copiedManifest = Get-ChildItem -LiteralPath $destinationPath -Recurse -File -Filter "manifest.json" | Select-Object -First 1
$copiedData = Get-Content -LiteralPath $copiedManifest.FullName -Raw | ConvertFrom-Json
if ($copiedData.pack_id -ne $ExpectedPackId -or @($copiedData.record_inventory).Count -ne $ExpectedRecords) {
    throw "Copied Knowledge Pack verification failed"
}
Write-Output "KNOWLEDGE_PACK_HOST_RECOVERY_PASS"
Write-Output "PACK_PATH=$destinationPath"
Write-Output "PACK_ID=$($copiedData.pack_id)"
Write-Output "RECORD_COUNT=$(@($copiedData.record_inventory).Count)"
