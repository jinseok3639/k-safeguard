param(
    [string]$ModelHome = "D:\local llm\guardrails",
    [switch]$Online
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Activate = Join-Path $RepoRoot ".venv-experiment\Scripts\Activate.ps1"

if (-not (Test-Path -LiteralPath $Activate)) {
    throw "실험 환경이 없습니다. 먼저 .\experiments\guardrail\setup.ps1 을 실행하세요."
}

$env:K_SAFEGUARD_MODEL_HOME = $ModelHome
$env:HF_HOME = Join-Path $ModelHome "hf-home"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$OfflineValue = if ($Online) { "0" } else { "1" }
$env:HF_HUB_OFFLINE = $OfflineValue
$env:TRANSFORMERS_OFFLINE = $OfflineValue
$env:TOKENIZERS_PARALLELISM = "false"

. $Activate
Write-Output "k-safeguard experiment environment activated"
Write-Output "Python:     $((Get-Command python).Source)"
Write-Output "Model home: $ModelHome"
Write-Output "Offline:    $(-not $Online)"
