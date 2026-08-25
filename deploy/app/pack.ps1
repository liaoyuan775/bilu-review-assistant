param(
    [string]$OutDir = ""
)
# Pack a single uploadable zip. Does not change local ports or stop local services.

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $OutDir) { $OutDir = Join-Path $Repo "dist-deploy" }
$Name = "bilu2-docker"
$Stage = Join-Path $OutDir $Name
$FixedZipName = "bilu2-docker.zip"

function Assert-FileContains {
    param([string]$Path, [string]$Needle, [string]$Hint)
    if (-not (Test-Path $Path)) { throw "[pack] missing file: $Path" }
    $text = [IO.File]::ReadAllText($Path)
    if ($text.IndexOf($Needle) -lt 0) {
        throw "[pack] $Hint | file=$Path | need=$Needle"
    }
}

function Assert-FileExists {
    param([string]$Path, [string]$Hint)
    if (-not (Test-Path $Path)) { throw "[pack] $Hint | missing=$Path" }
}

Write-Host "[..] preflight checks"

Assert-FileExists (Join-Path $Repo "backend\Dockerfile") "backend Dockerfile required"
Assert-FileExists (Join-Path $Repo "backend\requirements.txt") "backend requirements required"
Assert-FileExists (Join-Path $Repo "backend\.dockerignore") "backend dockerignore required"
Assert-FileExists (Join-Path $Repo "backend\app\main.py") "backend app required"
Assert-FileExists (Join-Path $Repo "backend\app\data\__init__.py") "app.data package required"
Assert-FileExists (Join-Path $Repo "backend\app\data\rules.py") "app.data.rules required"
Assert-FileExists (Join-Path $Repo "backend\app\data\domain_contracts.py") "app.data.domain_contracts required"
Assert-FileExists (Join-Path $Repo "backend\template_rules.json") "template rules required"
Assert-FileExists (Join-Path $Repo "backend\domain-contracts\header_procedure.json") "domain contracts required"
Assert-FileExists (Join-Path $Repo "backend\prompt-templates\domain-extraction.txt") "prompt template required"
Assert-FileExists (Join-Path $Repo "backend\prompt-templates\domains\online-money.txt") "domain prompts required"
$demoFiles = @(
    "01-baseline.docx",
    "02-line-breaks.docx",
    "03-blank-answer.docx",
    "04-long-answer.docx",
    "05-table-and-symbols.docx",
    "06-all-statuses-demo.docx"
)
foreach ($demo in $demoFiles) {
    Assert-FileExists (Join-Path $Repo "backend\test-fixtures\$demo") "runtime demo fixture required: $demo"
}
Assert-FileExists (Join-Path $Repo "frontend\package.json") "frontend package.json required"
Assert-FileExists (Join-Path $Repo "frontend\package-lock.json") "frontend package-lock.json required"
Assert-FileExists (Join-Path $Repo "frontend\public\fonts\noto-sans-sc-400.woff2") "bundled UI font required"
Assert-FileContains (Join-Path $PSScriptRoot "Dockerfile.frontend") "frontend/public" "Dockerfile must copy public/fonts into image"
Assert-FileContains (Join-Path $PSScriptRoot "nginx.conf") "location /fonts/" "nginx must serve bundled fonts"
Assert-FileExists (Join-Path $PSScriptRoot "deploy.sh") "deploy.sh required"
Assert-FileExists (Join-Path $PSScriptRoot "docker-compose.yml") "docker-compose.yml required"
Assert-FileExists (Join-Path $PSScriptRoot "Dockerfile.frontend") "Dockerfile.frontend required"
Assert-FileExists (Join-Path $PSScriptRoot "nginx.conf") "nginx.conf required"
Assert-FileExists (Join-Path $PSScriptRoot ".env.example") ".env.example required"

Assert-FileContains (Join-Path $Repo "backend\requirements.txt") "uvicorn" "Docker runtime needs uvicorn"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "mirrors.aliyun.com" "Dockerfile should use China mirrors"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "--mount=type=cache,target=/root/.cache/pip" "pip should use cache mount"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "COPY app ./app" "app code must enter the image"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "COPY template_rules.json" "template rules must enter the image"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "COPY domain-contracts" "domain contracts must enter the image"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "COPY prompt-templates" "prompt templates must enter the image"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "COPY test-fixtures/*.docx" "demo fixtures must enter the image"
Assert-FileContains (Join-Path $Repo "backend\Dockerfile") "from app.data.rules import TEMPLATE_RULES" "image build must import app.data"
Assert-FileContains (Join-Path $Repo "backend\.dockerignore") "/data/" "only runtime /data must be ignored, not app/data"
Assert-FileContains (Join-Path $PSScriptRoot "Dockerfile.frontend") "VITE_API_BASE_URL=" "frontend must use same-origin /api"
Assert-FileContains (Join-Path $PSScriptRoot "Dockerfile.frontend") "registry.npmmirror.com" "frontend npm should use China mirror"
Assert-FileContains (Join-Path $PSScriptRoot "nginx.conf") "proxy_pass http://backend:8787/api/" "nginx must proxy /api to backend"
Assert-FileContains (Join-Path $PSScriptRoot "docker-compose.yml") "FRONTEND_PORT:-5175" "page must be published on 5175"
Assert-FileContains (Join-Path $PSScriptRoot "docker-compose.yml") "BACKEND_PORT:-6678" "health port must be published on 6678"
Assert-FileContains (Join-Path $PSScriptRoot "docker-compose.yml") "name: bilu" "compose project name required"
Assert-FileContains (Join-Path $PSScriptRoot "deploy.sh") "docker compose" "deploy must use compose v2"
$deployText = [IO.File]::ReadAllText((Join-Path $PSScriptRoot "deploy.sh"))
if ($deployText.Contains("--no-cache") -and -not $deployText.Contains("FORCE_REBUILD")) {
    throw "[pack] deploy.sh default path must not use --no-cache"
}

$envExample = Join-Path $PSScriptRoot ".env.example"
Assert-FileContains $envExample "QWEN_BASE_URL=" "model endpoint must be baked into .env.example"
Assert-FileContains $envExample "GLnhmdSHlWYbxhnhmgR7zaTinZhIUc0kPcR9R93bzEo3xFYJMw" "API key must be baked into .env.example"
Assert-FileContains $envExample "QWEN_MODEL=" "model name must be baked into .env.example"
Assert-FileContains $envExample "QWEN_DOMAIN_CONCURRENCY=" "concurrency must be baked into .env.example"
Assert-FileContains $envExample "REVIEW_DATABASE_PATH=" "REVIEW_DATABASE_PATH must be baked into .env.example"
Assert-FileContains $envExample "DATABASE_URL=sqlite:////app/data/reviews.db" "DATABASE_URL must be baked into .env.example"
Assert-FileContains $envExample "FRONTEND_PORT=5175" "page port 5175 must be baked into .env.example"
Assert-FileContains $envExample "BACKEND_PORT=6678" "health-check port must be baked into .env.example"

if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

function Copy-CleanDir {
    param(
        [string]$Src,
        [string]$Dst,
        [string[]]$ExtraExcludeDirs = @()
    )
    New-Item -ItemType Directory -Force -Path $Dst | Out-Null
    $xd = @(
        ".venv", "__pycache__", ".pytest_cache", "node_modules", "dist",
        "tests", "test-fixtures", "test-results", "demotest", ".vite",
        "output", "logs"
    ) + $ExtraExcludeDirs
    $robocopyArgs = @(
        $Src, $Dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np",
        "/XD"
    ) + $xd + @(
        "/XF", ".env", ".env.development", ".env.production", ".env.local",
        "*.test.ts", "*.test.tsx", "*.tsbuildinfo", "*.log", "*.err.log", "*.out.log"
    )
    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $Src -> $Dst ($LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

Write-Host "[..] assemble $Name"

New-Item -ItemType Directory -Force -Path (Join-Path $Stage "backend") | Out-Null
Copy-Item (Join-Path $Repo "backend\requirements.txt") (Join-Path $Stage "backend\")
Copy-Item (Join-Path $Repo "backend\Dockerfile") (Join-Path $Stage "backend\")
Copy-Item (Join-Path $Repo "backend\.dockerignore") (Join-Path $Stage "backend\")
Copy-Item (Join-Path $Repo "backend\template_rules.json") (Join-Path $Stage "backend\")
Copy-CleanDir (Join-Path $Repo "backend\app") (Join-Path $Stage "backend\app") @("demotest")
Copy-CleanDir (Join-Path $Repo "backend\domain-contracts") (Join-Path $Stage "backend\domain-contracts")
Copy-CleanDir (Join-Path $Repo "backend\prompt-templates") (Join-Path $Stage "backend\prompt-templates")

$demoDst = Join-Path $Stage "backend\test-fixtures"
New-Item -ItemType Directory -Force -Path $demoDst | Out-Null
foreach ($demo in $demoFiles) {
    Copy-Item (Join-Path $Repo "backend\test-fixtures\$demo") $demoDst
}

Copy-CleanDir (Join-Path $Repo "frontend") (Join-Path $Stage "frontend")

$DeployDst = Join-Path $Stage "deploy\app"
New-Item -ItemType Directory -Force -Path $DeployDst | Out-Null
@(
    "docker-compose.yml", "Dockerfile.frontend", "nginx.conf", ".env.example"
) | ForEach-Object {
    Copy-Item (Join-Path $PSScriptRoot $_) $DeployDst
}

foreach ($sh in @("deploy.sh")) {
    $src = Join-Path $PSScriptRoot $sh
    $bytes = [IO.File]::ReadAllBytes($src)
    $text = [Text.Encoding]::UTF8.GetString($bytes) -replace "`r`n", "`n" -replace "`r", "`n"
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [IO.File]::WriteAllText((Join-Path $DeployDst $sh), $text, $utf8)
}

$rootIgnore = Join-Path $PSScriptRoot "root.dockerignore"
if (Test-Path $rootIgnore) {
    Copy-Item $rootIgnore (Join-Path $Stage ".dockerignore")
}

Assert-FileContains (Join-Path $Stage "backend\requirements.txt") "uvicorn" "packed requirements missing uvicorn"
Assert-FileExists (Join-Path $Stage "backend\app\data\__init__.py") "packed app.data package missing"
Assert-FileExists (Join-Path $Stage "backend\app\data\rules.py") "packed app.data.rules missing"
Assert-FileExists (Join-Path $Stage "backend\app\data\domain_contracts.py") "packed app.data.domain_contracts missing"
Assert-FileExists (Join-Path $Stage "backend\template_rules.json") "packed template rules missing"
Assert-FileExists (Join-Path $Stage "backend\domain-contracts\header_procedure.json") "packed domain contracts missing"
Assert-FileExists (Join-Path $Stage "backend\prompt-templates\domain-extraction.txt") "packed prompt template missing"
Assert-FileExists (Join-Path $Stage "backend\prompt-templates\domains\online-money.txt") "packed domain prompts missing"
Assert-FileContains (Join-Path $Stage "deploy\app\.env.example") "FRONTEND_PORT=5175" "packed .env.example missing 5175"
Assert-FileContains (Join-Path $Stage "deploy\app\.env.example") "DATABASE_URL=sqlite:////app/data/reviews.db" "packed .env.example missing DATABASE_URL"
Assert-FileExists (Join-Path $Stage "frontend\package-lock.json") "packed frontend lockfile missing"
if (Test-Path (Join-Path $Stage "frontend\.env.development")) {
    throw "[pack] frontend .env.development must not enter the zip"
}
if (Test-Path (Join-Path $Stage "backend\tests")) {
    throw "[pack] backend tests must not enter the zip"
}
if (Test-Path (Join-Path $Stage "backend\app\demotest")) {
    throw "[pack] backend demotest must not enter the zip"
}
if (Test-Path (Join-Path $Stage "frontend\tsconfig.app.tsbuildinfo")) {
    throw "[pack] frontend tsbuildinfo must not enter the zip"
}

$upload = @"
Bilu one-click deploy

On server:
  unzip -o bilu2-docker.zip
  cd bilu2-docker/deploy/app
  chmod +x deploy.sh && ./deploy.sh

Open:
  http://SERVER_IP:5175/
  http://SERVER_IP:6678/api/v1/health

Reuse cache: run ./deploy.sh only. Do NOT set FORCE_REBUILD=1.
If an old .env already exists, this script will not overwrite it.
Unpack a new zip into a new directory instead of reusing an incomplete old folder.
"@
[IO.File]::WriteAllText((Join-Path $Stage "UPLOAD_ME.txt"), $upload, (New-Object System.Text.UTF8Encoding $false))

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Zip = Join-Path $OutDir "$Name.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }

$zipPy = Join-Path $OutDir "_zip_pack.py"
$zipPyCode = @"
import zipfile, pathlib
stage = pathlib.Path(r'''$Stage''')
zip_path = pathlib.Path(r'''$Zip''')
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for p in stage.rglob('*'):
        if p.is_file():
            zf.write(p, p.relative_to(stage.parent).as_posix())
print('zip_ok', zip_path, 'bytes', zip_path.stat().st_size)
"@
[IO.File]::WriteAllText($zipPy, $zipPyCode, (New-Object System.Text.UTF8Encoding $false))

$py = $null
foreach ($candidate in @("python", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $py = $candidate
        break
    }
}
if (-not $py) { throw "python is required to create the zip" }
if ($py -eq "py") {
    & $py -3 $zipPy
} else {
    & $py $zipPy
}
if ($LASTEXITCODE -ne 0) { throw "zip failed" }
Remove-Item -Force $zipPy -ErrorAction SilentlyContinue

$RootZip = Join-Path $Repo $FixedZipName
Copy-Item -Force $Zip $RootZip
if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }

Get-ChildItem $Repo -Filter "bilu2-docker-*.zip" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne $FixedZipName } |
    Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $Repo -Directory -Filter "bilu2-docker-*" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[OK] package ready"
Write-Host "     ONLY zip: $RootZip"
Write-Host "     upload -> unzip -o bilu2-docker.zip -> cd bilu2-docker/deploy/app -> ./deploy.sh"
Write-Host "     open http://SERVER_IP:5175/  health http://SERVER_IP:6678/api/v1/health"
