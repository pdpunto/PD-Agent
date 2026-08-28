[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\dev\proyectos\PD-Agent',
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$PdAgentCommit
)

$ErrorActionPreference = 'Stop'
$ExpectedPackId = '9045db86cf29d54f526a918be95c74cc37db87597bcc443cfbdb6f396ca04ef1'
$ExpectedRecords = 104978
$ExpectedYarnSha = 'e8112359716235dc4fd7f0bd4a6162fd728e0d1067d9fa02f289edaaccd37718'
$ExpectedFabricApiSha = 'bdff7fd7e220085cfad2ff9b1f40dde6534ae0b96cf378f97a374bc54cb9ed0f'
$ExpectedConceptRevision = '1.21.11-curated-1'

function Invoke-GitValue {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $value = & git -C $RepoRoot @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git command failed: git -C $RepoRoot $($Arguments -join ' ')" }
    return ($value -join "`n").Trim()
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-FileHash {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Expected)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "required input is missing: $Path" }
    $actual = Get-Sha256 -Path $Path
    if ($actual -ne $Expected) { throw "input hash mismatch: path=$Path expected=$Expected actual=$actual" }
    return $actual
}

function Invoke-CapturedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$EvidenceRoot
    )
    $stdout = Join-Path $EvidenceRoot "$Label.stdout.txt"
    $stderr = Join-Path $EvidenceRoot "$Label.stderr.txt"
    $metaPath = Join-Path $EvidenceRoot "$Label.execution.json"
    $command = "& `"$FilePath`" " + (($Arguments | ForEach-Object { "`"$_`"" }) -join ' ')
    $start = [DateTime]::UtcNow
    $meta = [ordered]@{ label=$Label; command=$command; start_utc=$start.ToString('o'); end_utc=$null; elapsed_seconds=$null; exit_code=$null; timeout='none'; stdout=$stdout; stderr=$stderr }
    $meta | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $metaPath -Encoding UTF8
    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -RedirectStandardOutput $stdout -RedirectStandardError $stderr -NoNewWindow -Wait -PassThru
        $meta.exit_code = $process.ExitCode
    }
    finally {
        $end = [DateTime]::UtcNow
        $meta.end_utc = $end.ToString('o')
        $meta.elapsed_seconds = ($end - $start).TotalSeconds
        $meta | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $metaPath -Encoding UTF8
    }
    return [pscustomobject]@{ label=$Label; command=$command; stdout=$stdout; stderr=$stderr; meta=$metaPath; exit_code=$meta.exit_code }
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) { throw "RepoRoot does not exist: $RepoRoot" }
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) { throw "RepoRoot is not a Git worktree: $RepoRoot" }
$head = Invoke-GitValue -Arguments @('rev-parse', 'HEAD')
$originMain = Invoke-GitValue -Arguments @('rev-parse', 'origin/main')
if ($head.ToLowerInvariant() -ne $PdAgentCommit.ToLowerInvariant()) { throw "baseline mismatch: HEAD=$head expected=$PdAgentCommit" }
if ($originMain.ToLowerInvariant() -ne $PdAgentCommit.ToLowerInvariant()) { throw "baseline mismatch: origin/main=$originMain expected=$PdAgentCommit" }

$statusLines = @(& git -C $RepoRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw "git status failed for RepoRoot: $RepoRoot" }
$unexpectedStatus = @(
    foreach ($statusLine in $statusLines) {
        $line = [string]$statusLine
        if ($line.Length -lt 4) { $line; continue }
        $xy = $line.Substring(0, 2)
        $path = $line.Substring(3).Replace('\', '/')
        if ($xy -ne '??' -or $path -notmatch '^scripts/benchmark/diagnostics/.+') { $line }
    }
)
if ($unexpectedStatus.Count -gt 0) { throw "working tree is not clean; unexpected status: $($unexpectedStatus -join ' | ')" }

$python = Join-Path $RepoRoot '.venv-l0fix\Scripts\python.exe'
$materializer = Join-Path $RepoRoot 'scripts\benchmark\materialize_frozen_knowledge.py'
$concepts = Join-Path $RepoRoot 'src\pd_agent\brain\concepts.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Python executable is missing: $python" }
if (-not (Test-Path -LiteralPath $materializer -PathType Leaf)) { throw "materializer is missing: $materializer" }
if (-not (Test-Path -LiteralPath $concepts -PathType Leaf)) { throw "concept source is missing: $concepts" }

$seedRoot = 'C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.8-i15-canonical-seed-recovered-f650605ed17f4b2292adb26b07deae02\seed'
$yarn = Join-Path $seedRoot 'caches\modules-2\files-2.1\net.fabricmc\yarn\1.21.11+build.6\623a9304295dc0128e0543b558bb46c01ac81959\yarn-1.21.11+build.6-v2.jar'
$fabricApi = Join-Path $seedRoot 'caches\modules-2\files-2.1\net.fabricmc.fabric-api\fabric-api\0.141.6+1.21.11\c98467cbbaf4d197377266795ae015f4130d65b6\fabric-api-0.141.6+1.21.11.jar'
$yarnSha = Assert-FileHash -Path $yarn -Expected $ExpectedYarnSha
$fabricApiSha = Assert-FileHash -Path $fabricApi -Expected $ExpectedFabricApiSha
$conceptText = Get-Content -LiteralPath $concepts -Raw
if ($conceptText -notmatch ('artifact_version\s*=\s*["'']' + [regex]::Escape($ExpectedConceptRevision) + '["'']')) { throw "concept revision mismatch: expected=$ExpectedConceptRevision" }

$launchRoot = Join-Path $env:TEMP ('pd-agent-v0.8-i16-knowledge-pack-host-' + [guid]::NewGuid().ToString('N'))
$evidence = Join-Path $launchRoot 'evidence'
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$loader = Join-Path $evidence 'validate_pack_loader.py'
$loaderCode = @'
import hashlib
import json
import os
from pathlib import Path

from pd_agent.brain.frozen import load_frozen_knowledge_pack

pack_path = Path(os.environ["PD_I16_PACK_PATH"])
expected_records = int(os.environ["PD_I16_EXPECTED_RECORDS"])
manifest = json.loads((pack_path / "manifest.json").read_text(encoding="utf-8"))
record_files = sorted((pack_path / "records").glob("*.json"))
pack = load_frozen_knowledge_pack(pack_path)
if len(record_files) != expected_records or len(pack.records) != expected_records:
    raise SystemExit(f"record count mismatch: files={len(record_files)} loaded={len(pack.records)} expected={expected_records}")
inventory = manifest["record_inventory"]
identity_values = sorted(str(item["record_identity"]) for item in inventory)
inventory_hash = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
identity_hash = hashlib.sha256(json.dumps(identity_values, separators=(",", ":")).encode("utf-8")).hexdigest()
retrieved_non_null = sum(1 for record in pack.records if record.provenance.retrieved_at is not None)
retrieved_null = len(pack.records) - retrieved_non_null
print(json.dumps({"loader":"PASS", "pack_id":pack.manifest.pack_id, "records":len(pack.records), "inventory_hash":inventory_hash, "record_identity_hash":identity_hash, "retrieved_at_non_null":retrieved_non_null, "retrieved_at_null":retrieved_null}, sort_keys=True))
'@
[System.IO.File]::WriteAllText($loader, $loaderCode, [System.Text.UTF8Encoding]::new($false))
& $python -m py_compile $loader
if ($LASTEXITCODE -ne 0) { throw "loader helper py_compile failed; evidence preserved at $evidence" }

$runs = @()
foreach ($label in @('A', 'B')) {
    $destination = Join-Path $launchRoot "pack-$label"
    if (Test-Path -LiteralPath $destination) { throw "destination already exists: $destination" }
    $material = Invoke-CapturedProcess -Label "materializer-$label" -FilePath $python -Arguments @($materializer, '--yarn-artifact', $yarn, '--fabric-api-artifact', $fabricApi, '--output', $destination) -EvidenceRoot $evidence
    if ($material.exit_code -ne 0) { throw "materializer $label failed with exit code $($material.exit_code); evidence preserved at $evidence" }
    $env:PD_I16_PACK_PATH = $destination
    $env:PD_I16_EXPECTED_RECORDS = [string]$ExpectedRecords
    $load = Invoke-CapturedProcess -Label "loader-$label" -FilePath $python -Arguments @($loader) -EvidenceRoot $evidence
    if ($load.exit_code -ne 0) { throw "loader $label failed with exit code $($load.exit_code); evidence preserved at $evidence" }
    $loaderJson = Get-Content -Raw -LiteralPath $load.stdout | ConvertFrom-Json
    $manifestPath = Join-Path $destination 'manifest.json'
    $recordsPath = Join-Path $destination 'records'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "manifest missing for $label" }
    if (-not (Test-Path -LiteralPath $recordsPath -PathType Container)) { throw "records missing for $label" }
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    $recordFiles = @(Get-ChildItem -LiteralPath $recordsPath -Filter '*.json' -File)
    if ($recordFiles.Count -ne $ExpectedRecords) { throw "record count mismatch for $label" }
    $runs += [ordered]@{ label=$label; destination=$destination; pack_id=[string]$manifest.pack_id; records=$recordFiles.Count; inventory_hash=[string]$loaderJson.inventory_hash; record_identity_hash=[string]$loaderJson.record_identity_hash; retrieved_at_non_null=[int]$loaderJson.retrieved_at_non_null; retrieved_at_null=[int]$loaderJson.retrieved_at_null; loader='PASS'; materializer=$material; loader_evidence=$load }
}

$deterministic = $runs[0].pack_id -eq $runs[1].pack_id -and $runs[0].records -eq $runs[1].records -and $runs[0].inventory_hash -eq $runs[1].inventory_hash -and $runs[0].record_identity_hash -eq $runs[1].record_identity_hash
$historicalMatch = $runs[0].pack_id -eq $ExpectedPackId
$summary = [ordered]@{ status=if($deterministic){'DETERMINISTIC_CURRENT_PACK'}else{'CURRENT_PACK_NONDETERMINISTIC'}; matches_historical_pack=if($historicalMatch){'YES'}else{'NO'}; historical_pack_id=$ExpectedPackId; expected_records=$ExpectedRecords; launch_root=$launchRoot; evidence=$evidence; runs=$runs; network='NOT_USED' }
$summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $evidence 'summary.json') -Encoding UTF8
Write-Output "LAUNCH_ROOT=$launchRoot"
Write-Output "EVIDENCE=$evidence"
Write-Output "PACK_A=$($runs[0].pack_id) RECORDS_A=$($runs[0].records) LOADER_A=PASS"
Write-Output "PACK_B=$($runs[1].pack_id) RECORDS_B=$($runs[1].records) LOADER_B=PASS"
Write-Output "DETERMINISTIC_CURRENT_PACK=$(if($deterministic){'YES'}else{'NO'})"
Write-Output "MATCHES_HISTORICAL_PACK=$(if($historicalMatch){'YES'}else{'NO'})"
Write-Output "I16_KNOWLEDGE_PACK_HOST_MATERIALIZATION=$(if($deterministic){'DETERMINISTIC_CURRENT_PACK'}else{'CURRENT_PACK_NONDETERMINISTIC'})"
