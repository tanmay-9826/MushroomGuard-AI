$ErrorActionPreference = 'Stop'

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not installed. Install Git for Windows first.' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is not installed. Install it, then run gh auth login.' }
& git lfs version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Git LFS is required for the included dataset images. Install Git LFS first.' }

Write-Host 'This script publishes the current folder as a PUBLIC GitHub repository.' -ForegroundColor Yellow
Write-Host 'Review GITHUB_PUBLICATION.md, DATASET_AUDIT_2026-11-04.md and the absence of a LICENSE before continuing.'
$confirm = Read-Host 'Type PUBLIC to confirm you intend to publish this repository publicly'
if ($confirm -cne 'PUBLIC') { Write-Host 'Cancelled.'; exit 0 }

& git lfs install
if (-not (Test-Path '.git')) { & git init -b main }
& git add .gitattributes
& git add .
& git status --short
& git lfs ls-files

$commit = Read-Host 'Type COMMIT to create the initial local commit'
if ($commit -cne 'COMMIT') { Write-Host 'Staged locally but not committed. Review with git status.'; exit 0 }
& git commit -m 'Prepare MushroomGuard AI source and Methi dataset'
if ($LASTEXITCODE -ne 0) { throw 'Git commit failed. Check git identity and status.' }

& gh auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI is not authenticated. Run gh auth login and rerun this script.' }
& gh repo create MushroomGuard-AI --public --source . --remote origin --push --description 'Offline-first mushroom and microgreens cultivation monitoring with Arduino, Flask and Methi dataset tooling'
if ($LASTEXITCODE -ne 0) { throw 'GitHub repo creation/push failed. Check whether the repository name already exists and whether Git LFS quota is available.' }
Write-Host 'Published. Verify the repository contents and Git LFS files on GitHub.' -ForegroundColor Green
