param([ValidateSet('install','preflight','diagnostics','status','check','start','stop','restart','uninstall')][string]$Action = 'install', [switch]$Unattended)
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    if ($Unattended -and $Action -ne 'install') { throw 'Unattended applies only to install.' }
    $setupArgs = @($Action)
    if ($Unattended) { $setupArgs += '--unattended' }
    $python = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
    if ($Action -ne 'install' -and (Test-Path -LiteralPath $python -PathType Leaf)) {
        & $python scripts/setup.py @setupArgs
        exit $LASTEXITCODE
    }
    $version = '0.13.10'
    $arch = switch ($env:PROCESSOR_ARCHITECTURE) {
        'AMD64' { 'x86_64' }
        'ARM64' { 'aarch64' }
        default { throw 'Unsupported Windows architecture. Use native 64-bit PowerShell.' }
    }
    $digests = @{
        x86_64 = '297b3881fe1adfb922becc2c1613202abb41dc83ea5ff43d472aa087ca1f8683'
        aarch64 = 'f223bcd3fa010174ffeeb885cc1d5334bb81388640c65baa5b8b42b47017337e'
    }
    $localUv = Join-Path (Get-Location).Path ".bootstrap\uv-$version.exe"
    $existing = Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($existing) { $uv = $existing.Source }
    elseif (Test-Path -LiteralPath $localUv -PathType Leaf) { $uv = $localUv }
    else {
        $scratch = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
        New-Item -ItemType Directory -Path $scratch | Out-Null
        try {
            $name = "uv-$arch-pc-windows-msvc.zip"
            $zip = Join-Path $scratch $name
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$version/$name" -OutFile $zip -TimeoutSec 180
            if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne $digests[$arch]) { throw 'uv checksum mismatch' }
            Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $scratch 'out')
            $exe = @(Get-ChildItem -Path (Join-Path $scratch 'out') -Filter uv.exe -Recurse -File)
            if ($exe.Count -ne 1) { throw 'Unexpected uv archive layout' }
            New-Item -ItemType Directory -Path (Split-Path $localUv) -Force | Out-Null
            Copy-Item -LiteralPath $exe[0].FullName -Destination $localUv
            $uv = $localUv
        } finally { Remove-Item -LiteralPath $scratch -Recurse -Force }
    }
    $env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location).Path '.venv'
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    & $uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
    & $uv run --frozen --python 3.12 python scripts/setup.py @setupArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
