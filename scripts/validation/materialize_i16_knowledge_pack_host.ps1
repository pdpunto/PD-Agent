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
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git -C $RepoRoot $($Arguments -join ' ')"
    }
    return ($value -join "`n").Trim()
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "required input is missing: $Path"
    }
    $actual = Get-Sha256 -Path $Path
    if ($actual -ne $Expected) {
        throw "input hash mismatch: path=$Path expected=$Expected actual=$actual"
    }
    return $actual
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "RepoRoot does not exist: $RepoRoot"
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) {
    throw "RepoRoot is not a Git worktree: $RepoRoot"
}

$head = Invoke-GitValue -Arguments @('rev-parse', 'HEAD')
$originMain = Invoke-GitValue -Arguments @('rev-parse', 'origin/main')
if ($head.ToLowerInvariant() -ne $PdAgentCommit.ToLowerInvariant()) {
    throw "baseline mismatch: HEAD=$head expected=$PdAgentCommit"
}
if ($originMain.ToLowerInvariant() -ne $PdAgentCommit.ToLowerInvariant()) {
    throw "baseline mismatch: origin/main=$originMain expected=$PdAgentCommit"
}

$statusLines = @(& git -C $RepoRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "git status failed for RepoRoot: $RepoRoot"
}
$unexpectedStatus = @(
    foreach ($statusLine in $statusLines) {
        $line = [string]$statusLine
        if ($line.Length -lt 4) {
            $line
            continue
        }
        $xy = $line.Substring(0, 2)
        $path = $line.Substring(3).Replace('\', '/')
        if ($xy -ne '??' -or $path -notmatch '^scripts/benchmark/diagnostics/.+') {
            $line
        }
    }
)
if ($unexpectedStatus.Count -gt 0) {
    throw "working tree is not clean; unexpected status: $($unexpectedStatus -join ' | ')"
}

$python = Join-Path $RepoRoot '.venv-l0fix\Scripts\python.exe'
$materializer = Join-Path $RepoRoot 'scripts\benchmark\materialize_frozen_knowledge.py'
$concepts = Join-Path $RepoRoot 'src\pd_agent\brain\concepts.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python executable is missing: $python"
}
if (-not (Test-Path -LiteralPath $materializer -PathType Leaf)) {
    throw "materializer is missing: $materializer"
}
if (-not (Test-Path -LiteralPath $concepts -PathType Leaf)) {
    throw "concept source is missing: $concepts"
}

$seedRoot = 'C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.8-i15-canonical-seed-recovered-f650605ed17f4b2292adb26b07deae02\seed'
$yarn = Join-Path $seedRoot 'caches\modules-2\files-2.1\net.fabricmc\yarn\1.21.11+build.6\623a9304295dc0128e0543b558bb46c01ac81959\yarn-1.21.11+build.6-v2.jar'
$fabricApi = Join-Path $seedRoot 'caches\modules-2\files-2.1\net.fabricmc.fabric-api\fabric-api\0.141.6+1.21.11\c98467cbbaf4d197377266795ae015f4130d65b6\fabric-api-0.141.6+1.21.11.jar'
$yarnSha = Assert-FileHash -Path $yarn -Expected $ExpectedYarnSha
$fabricApiSha = Assert-FileHash -Path $fabricApi -Expected $ExpectedFabricApiSha

$conceptText = Get-Content -LiteralPath $concepts -Raw
if ($conceptText -notmatch ('artifact_version\s*=\s*["'']' + [regex]::Escape($ExpectedConceptRevision) + '["'']')) {
    throw "concept revision mismatch: expected=$ExpectedConceptRevision"
}

$launchRoot = Join-Path $env:TEMP ('pd-agent-v0.8-i16-knowledge-pack-host-' + [guid]::NewGuid().ToString('N'))
$destination = Join-Path $launchRoot 'pack'
$evidence = Join-Path $launchRoot 'evidence'
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
if (Test-Path -LiteralPath $destination) {
    throw "new destination unexpectedly exists: $destination"
}

$materializerStdout = Join-Path $evidence 'materializer.stdout.txt'
$materializerStderr = Join-Path $evidence 'materializer.stderr.txt'
$materializerMeta = Join-Path $evidence 'materializer.execution.json'
$command = "& `"$python`" `"$materializer`" --yarn-artifact `"$yarn`" --fabric-api-artifact `"$fabricApi`" --output `"$destination`""
$start = [DateTime]::UtcNow
$meta = [ordered]@{
    command = $command
    start_utc = $start.ToString('o')
    repo_root = $RepoRoot
    head = $head
    origin_main = $originMain
    pd_agent_commit = $PdAgentCommit.ToLowerInvariant()
    yarn_artifact = $yarn
    yarn_sha256 = $yarnSha
    fabric_api_artifact = $fabricApi
    fabric_api_sha256 = $fabricApiSha
    concept_revision = $ExpectedConceptRevision
    destination = $destination
    evidence = $evidence
    timeout = 'none'
    exit_code = $null
    end_utc = $null
    elapsed_seconds = $null
}
$meta | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $materializerMeta -Encoding UTF8

try {
    $process = Start-Process -FilePath $python -ArgumentList @(
        $materializer, '--yarn-artifact', $yarn, '--fabric-api-artifact', $fabricApi, '--output', $destination
    ) -RedirectStandardOutput $materializerStdout -RedirectStandardError $materializerStderr -NoNewWindow -Wait -PassThru
    $meta.exit_code = $process.ExitCode
}
finally {
    $end = [DateTime]::UtcNow
    $meta.end_utc = $end.ToString('o')
    $meta.elapsed_seconds = ($end - $start).TotalSeconds
    $meta | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $materializerMeta -Encoding UTF8
}

Write-Output "MATERIALIZER_COMMAND=$command"
Write-Output "MATERIALIZER_START_UTC=$($meta.start_utc)"
Write-Output "MATERIALIZER_END_UTC=$($meta.end_utc)"
Write-Output "MATERIALIZER_ELAPSED_SECONDS=$($meta.elapsed_seconds)"
Write-Output "MATERIALIZER_EXIT_CODE=$($meta.exit_code)"
Write-Output "DESTINATION=$destination"
Write-Output "EVIDENCE=$evidence"
Write-Output '--- MATERIALIZER STDOUT ---'
if (Test-Path -LiteralPath $materializerStdout) { Get-Content -Raw -LiteralPath $materializerStdout }
Write-Output '--- MATERIALIZER STDERR ---'
if (Test-Path -LiteralPath $materializerStderr) { Get-Content -Raw -LiteralPath $materializerStderr }

if ($meta.exit_code -ne 0) {
    Write-Output 'I16_KNOWLEDGE_PACK_HOST_MATERIALIZATION=FAILED'
    throw "materializer failed with exit code $($meta.exit_code); evidence preserved at $evidence"
}

$manifestPath = Join-Path $destination 'manifest.json'
$recordsPath = Join-Path $destination 'records'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "successful materializer produced no manifest: $manifestPath"
}
if (-not (Test-Path -LiteralPath $recordsPath -PathType Container)) {
    throw "successful materializer produced no records directory: $recordsPath"
}

$loader = Join-Path $evidence 'validate_pack_loader.py'
$loaderStdout = Join-Path $evidence 'loader.stdout.txt'
$loaderStderr = Join-Path $evidence 'loader.stderr.txt'
$loaderCode = @'
import json
import os
from pathlib import Path

from pd_agent.brain.frozen import load_frozen_knowledge_pack

pack_path = Path(os.environ["PD_I16_PACK_PATH"])
expected_id = os.environ["PD_I16_EXPECTED_PACK_ID"]
expected_records = int(os.environ["PD_I16_EXPECTED_RECORDS"])
manifest = json.loads((pack_path / "manifest.json").read_text(encoding="utf-8"))
record_files = sorted((pack_path / "records").glob("*.json"))
pack = load_frozen_knowledge_pack(pack_path, expected_pack_id=expected_id)
if len(record_files) != expected_records or len(pack.records) != expected_records:
    raise SystemExit(f"record count mismatch: files={len(record_files)} loaded={len(pack.records)} expected={expected_records}")
if manifest.get("pack_id") != expected_id:
    raise SystemExit(f"pack id mismatch: actual={manifest.get('pack_id')} expected={expected_id}")
print(json.dumps({"loader": "PASS", "pack_id": pack.manifest.pack_id, "records": len(pack.records)}, sort_keys=True))
'@
[System.IO.File]::WriteAllText($loader, $loaderCode, [System.Text.UTF8Encoding]::new($false))
& $python -m py_compile $loader
if ($LASTEXITCODE -ne 0) {
    throw "loader helper py_compile failed; evidence preserved at $evidence"
}

$env:PD_I16_PACK_PATH = $destination
$env:PD_I16_EXPECTED_PACK_ID = $ExpectedPackId
$env:PD_I16_EXPECTED_RECORDS = [string]$ExpectedRecords
& $python $loader 1> $loaderStdout 2> $loaderStderr
$loaderExit = $LASTEXITCODE
Write-Output "LOADER_EXIT_CODE=$loaderExit"
if (Test-Path -LiteralPath $loaderStdout) { Write-Output "LOADER_STDOUT=$((Get-Content -Raw -LiteralPath $loaderStdout).Trim())" }
if (Test-Path -LiteralPath $loaderStderr) { Write-Output "LOADER_STDERR=$((Get-Content -Raw -LiteralPath $loaderStderr).Trim())" }
if ($loaderExit -ne 0) {
    throw "real pack loader validation failed; evidence preserved at $evidence"
}

$manifestData = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$recordFiles = @(Get-ChildItem -LiteralPath $recordsPath -Filter '*.json' -File)
if ($manifestData.pack_id -ne $ExpectedPackId) {
    throw "pack identity mismatch: actual=$($manifestData.pack_id) expected=$ExpectedPackId"
}
if ($recordFiles.Count -ne $ExpectedRecords) {
    throw "record inventory mismatch: actual=$($recordFiles.Count) expected=$ExpectedRecords"
}

$summary = [ordered]@{
    status = 'EXACT_HISTORICAL_PACK_REPRODUCED'
    pack_id = $manifestData.pack_id
    records = $recordFiles.Count
    manifest = $manifestPath
    destination = $destination
    evidence = $evidence
    loader = 'PASS'
    network = 'NOT_USED'
}
$summaryPath = Join-Path $evidence 'summary.json'
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
Write-Output "PACK_ID=$($manifestData.pack_id)"
Write-Output "RECORDS=$($recordFiles.Count)"
Write-Output "LOADER=PASS"
Write-Output "I16_KNOWLEDGE_PACK_HOST_MATERIALIZATION=EXACT_HISTORICAL_PACK_REPRODUCED"
