param(
    [string]$Python = 'python',
    [string]$HomeDirectory = '',
    [string]$ReplaceFrom = '',
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$venv = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    & $Python -m venv (Join-Path $repo '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
}
& $venv -m pip install -e $repo
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
Push-Location -LiteralPath $repo
try {
    & $venv -m rea_enhanced bootstrap
    if ($LASTEXITCODE -ne 0) { throw 'Pinned runtime preparation failed' }
    if (-not $PrepareOnly) {
        $installArguments = @('-m','rea_enhanced','install')
        if ($HomeDirectory) { $installArguments += @('--home', $HomeDirectory) }
        if ($ReplaceFrom) { $installArguments += @('--replace-from', $ReplaceFrom) }
        & $venv @installArguments
        if ($LASTEXITCODE -ne 0) { throw 'Managed installation failed; review its restoration report' }
    }
} finally { Pop-Location }
