param([Parameter(Mandatory=$true)][string]$Receipt)
& (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe') -m rea_enhanced rollback --receipt $Receipt
exit $LASTEXITCODE
