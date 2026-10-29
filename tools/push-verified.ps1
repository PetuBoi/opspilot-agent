param([string]$GitHubCli = 'gh')
$ErrorActionPreference = 'Stop'
$expectedOwner = 'PetuBoi'
$expectedName = 'opspilot-agent'
$expectedRemote = "https://github.com/$expectedOwner/$expectedName"
$expectedRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\', '/')
& $GitHubCli auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication failed' }
$account = & $GitHubCli api user --jq .login
if ($LASTEXITCODE -ne 0 -or $account -cne $expectedOwner) { throw 'Wrong GitHub account' }
$currentDirectory = (Get-Location).Path.TrimEnd('\', '/')
$root = (git rev-parse --show-toplevel).Replace('/', '\').TrimEnd('\')
$branch = git branch --show-current
$origin = git remote get-url origin
Write-Output "Directory: $currentDirectory`nRoot: $root`nBranch: $branch`nOrigin: $origin"
if ($currentDirectory -ine $expectedRoot -or $root -ine $expectedRoot) { throw 'Wrong repository root' }
if ($branch -cne 'main' -or $origin -cne $expectedRemote) { throw 'Wrong branch or origin' }
$owner = & $GitHubCli repo view "$expectedOwner/$expectedName" --json owner --jq .owner.login
if ($LASTEXITCODE -ne 0 -or $owner -cne $expectedOwner) { throw 'Target owner verification failed' }
git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Push failed' }
$local = git rev-parse HEAD
$remote = (git ls-remote origin refs/heads/main).Split("`t")[0]
if ($LASTEXITCODE -ne 0 -or $local -cne $remote) { throw 'Remote commit verification failed' }
Write-Output "Verified pushed HEAD: $local"
