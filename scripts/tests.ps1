$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$python = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} else {
    "python"
}

& $python -m vyper -f abi src\AegisInsuranceProtocol.vy | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python scripts\check_contract_size.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pytest
exit $LASTEXITCODE
