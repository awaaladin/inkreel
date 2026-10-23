# Builds the studio. node_modules lives in a build folder on C: (fast); the finished site is written to studio/dist next to this script.
# Usage: powershell -File build-studio.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$b = Join-Path $env:USERPROFILE "inkreel-build"
New-Item -ItemType Directory -Force $b | Out-Null
Copy-Item "$here\studio\package.json", "$here\studio\tsconfig.json", "$here\studio\vite.config.ts", "$here\studio\index.html" $b -Force
robocopy "$here\studio\public" "$b\public" /E /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy "$here\studio\src" "$b\src" /E /PURGE /NFL /NDL /NJH /NJS /NP | Out-Null
Push-Location $b
if (-not (Test-Path node_modules\vite)) { npm install --no-audit --no-fund --silent }
npx tsc --noEmit
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "typecheck failed" }
npx vite build --outDir "$here\studio\dist" --emptyOutDir
Pop-Location
