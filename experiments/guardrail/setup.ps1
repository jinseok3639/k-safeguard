param(
    [string]$ModelHome = "D:\local llm\guardrails",
    [string]$PythonCommand = "python",
    [switch]$SkipTorch
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvPath = Join-Path $RepoRoot ".venv-experiment"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$Requirements = Join-Path $PSScriptRoot "requirements.txt"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description 실패 (exit code: $LASTEXITCODE)"
    }
}

New-Item -ItemType Directory -Force -Path $ModelHome | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ModelHome "models") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ModelHome "hf-home") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ModelHome "offload") | Out-Null

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Invoke-Checked { & $PythonCommand -m venv $VenvPath } "가상환경 생성"
}

Invoke-Checked { & $VenvPython -m pip install --upgrade pip } "pip 업그레이드"

if (-not $SkipTorch) {
    # RTX 50 계열(Blackwell)은 CUDA 13.0 wheel을 사용한다.
    Invoke-Checked {
        & $VenvPython -m pip install "torch==2.13.0" --index-url https://download.pytorch.org/whl/cu130
    } "PyTorch 설치"
}

Invoke-Checked { & $VenvPython -m pip install --requirement $Requirements } "실험 의존성 설치"
Invoke-Checked { & $VenvPython -m pip install --editable $RepoRoot } "k-safeguard editable 설치"

$env:K_SAFEGUARD_MODEL_HOME = $ModelHome
$env:HF_HOME = Join-Path $ModelHome "hf-home"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:TOKENIZERS_PARALLELISM = "false"

Write-Output "Experiment Python: $VenvPython"
Write-Output "Model home:       $ModelHome"
Invoke-Checked {
    & $VenvPython -c "import torch, transformers, huggingface_hub; print(f'torch={torch.__version__} cuda={torch.version.cuda} cuda_available={torch.cuda.is_available()}'); print(f'transformers={transformers.__version__} huggingface_hub={huggingface_hub.__version__}'); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA GPU not available')"
} "환경 검증"
