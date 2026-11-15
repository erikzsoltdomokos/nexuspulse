# Rebuild and publish the static NexusPulse demo to GitHub Pages (gh-pages branch).
#
# Usage (from the repo root or anywhere):
#   powershell -ExecutionPolicy Bypass -File backend\scripts\deploy_pages.ps1            # build, export, commit, push
#   powershell -ExecutionPolicy Bypass -File backend\scripts\deploy_pages.ps1 -NoPush    # stop before pushing
#
# Steps: npm run build:static -> scripts\export_static.py (precomputed API JSON) -> copy into a
# git worktree of the orphan gh-pages branch (backend\data\gh-pages, git-ignored) -> commit ->
# git push origin gh-pages -> make sure Pages serves gh-pages:/ .
param([switch]$NoPush)

# Native tools (git, npm, gh) write progress to stderr; failures are checked via $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$frontend = Join-Path $root 'frontend'
$backend = Join-Path $root 'backend'
$dist = Join-Path $frontend 'dist-static'
$wt = Join-Path $backend 'data\gh-pages'
$repo = 'erikzsoltdomokos/nexuspulse'

Push-Location $frontend
try {
    if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
    npm.cmd run build:static
    if ($LASTEXITCODE -ne 0) { throw 'static frontend build failed' }
} finally { Pop-Location }

Push-Location $backend
try {
    & .\.venv\Scripts\python.exe scripts\export_static.py --out $dist
    if ($LASTEXITCODE -ne 0) { throw 'static export failed' }
} finally { Pop-Location }

if (-not (Test-Path (Join-Path $wt '.git'))) {
    git -C $root worktree prune
    git -C $root show-ref --verify --quiet refs/heads/gh-pages
    if ($LASTEXITCODE -eq 0) {
        git -C $root worktree add $wt gh-pages
    } else {
        git -C $root fetch origin gh-pages 2>$null
        if ($LASTEXITCODE -eq 0) { git -C $root worktree add -b gh-pages $wt origin/gh-pages }
        else { git -C $root worktree add --orphan -b gh-pages $wt }
    }
    if ($LASTEXITCODE -ne 0) { throw 'could not create the gh-pages worktree' }
}

Get-ChildItem -Force $wt | Where-Object { $_.Name -ne '.git' } | Remove-Item -Recurse -Force
Copy-Item -Recurse -Force (Join-Path $dist '*') $wt
New-Item -ItemType File -Force (Join-Path $wt '.nojekyll') | Out-Null

git -C $wt add -A
git -C $wt diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $src = (git -C $root rev-parse --short HEAD)
    git -C $wt commit -m "Static demo build from $src"
} else {
    Write-Host 'gh-pages: no changes to commit'
}

if ($NoPush) { Write-Host "Built into $wt; push with: git -C `"$wt`" push origin gh-pages"; exit 0 }

git -C $wt push origin gh-pages
if ($LASTEXITCODE -ne 0) { throw 'push failed' }

gh api "repos/$repo/pages" --silent 2>$null
if ($LASTEXITCODE -eq 0) {
    gh api -X PUT "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" --silent
} else {
    gh api -X POST "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" --silent
}
Write-Host 'Deployed: https://erikzsoltdomokos.github.io/nexuspulse/'
