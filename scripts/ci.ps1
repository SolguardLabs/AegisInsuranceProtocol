$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$python = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} else {
    "python"
}

& $python -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m compileall -q src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m vyper -f abi src\AegisInsuranceProtocol.vy | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python scripts\check_contract_size.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pytest --cov=aegis_protocol --cov-report=term-missing
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python scripts\check_loc.py
exit $LASTEXITCODE
