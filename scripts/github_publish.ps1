# ============================================================
# Project LUMI —— 一键把本地工程推上 GitHub 并触发 iOS 构建
#
# 为什么需要手动跑一次：
#   自动化环境里的 Edge 登录态受 Windows App-Bound 加密保护，
#   无法被其它进程复用；GitHub 的设备码授权也必须由人点一次「Authorize」。
#   这是平台的安全设计，不是代码缺陷。
#
# 用法（在 D:\ProjectLUMI 目录下打开 PowerShell）：
#   powershell -ExecutionPolicy Bypass -File scripts\github_publish.ps1
#
# 它会做四件事：
#   1. 检查 git 状态，确认没有未提交改动
#   2. 用 gh 登录（浏览器里点一次 Authorize）
#   3. 创建私有仓库并把 night/v0.3 分支推上去
#   4. 触发 iOS Build workflow，并给出查看链接
# ============================================================

$ErrorActionPreference = "Stop"
$RepoName = "ProjectLUMI"

Write-Host "== 1/4 检查仓库 ==" -ForegroundColor Cyan
$branch = git rev-parse --abbrev-ref HEAD
$dirty = git status --porcelain
if ($dirty) {
    Write-Host "工作区有未提交改动，请先提交（git add -A; git commit -m '...'）" -ForegroundColor Yellow
    git status --short
    exit 1
}
Write-Host "分支：$branch  提交：$(git rev-parse --short HEAD)"

Write-Host "== 2/4 检查 gh 与登录状态 ==" -ForegroundColor Cyan
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    Write-Host "未找到 gh。请先安装 GitHub CLI：" -ForegroundColor Yellow
    Write-Host "  winget install --id GitHub.cli -e"
    exit 1
}
gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "需要登录 GitHub（浏览器会打开，输入一次性码并点 Authorize）：" -ForegroundColor Yellow
    gh auth login --hostname github.com --git-protocol https --web
    gh auth setup-git
}

Write-Host "== 3/4 创建仓库并推送 ==" -ForegroundColor Cyan
$exists = gh repo view "$RepoName" 2>$null
if ($LASTEXITCODE -ne 0) {
    gh repo create $RepoName --private --source=. --remote=origin --push
} else {
    if (-not (git remote get-url origin 2>$null)) {
        gh repo set-default "$RepoName"
        git remote add origin "https://github.com/$((gh api user --jq .login))/$RepoName.git"
    }
    git push -u origin $branch
}

Write-Host "== 4/4 触发 iOS 构建 ==" -ForegroundColor Cyan
gh workflow run ios-build.yml --ref $branch
Start-Sleep -Seconds 3
gh run list --workflow=ios-build.yml --limit 3
Write-Host ""
Write-Host "构建进度：gh run watch" -ForegroundColor Green
Write-Host "产物下载：gh run download <run-id> -n LUMI-unsigned-ipa" -ForegroundColor Green
Write-Host ""
Write-Host "注意：未签名的 IPA 需要 SideStore / Sideloadly 在你自己的 Apple ID 下重签后才能装进 iPhone。" -ForegroundColor Yellow
