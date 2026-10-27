# Submit feiyu-chat-companion to awesome-dsh-plugin: fork -> branch -> one file -> PR.
# ASCII only on purpose: Windows PowerShell 5.1 reads scripts as ANSI and mangles
# any Chinese path literal. All CJK content is read from files with explicit UTF8.
$ErrorActionPreference = "Stop"

$UP     = "awesome-dsh-plugin/awesome-dsh-plugin"
$ME     = "AirPineApplea"
$FORK   = "$ME/awesome-dsh-plugin"
$FILE   = "data/plugins/${ME}__feiyu-chat-companion.yml"
$BRANCH = "add-feiyu-chat-companion"
$ENTRY  = "D:\dsh-web-pet\tools\entry.yml"
$BODY   = "D:\dsh-web-pet\tools\pr_body.md"

$cred = "protocol=https`nhost=github.com`n`n" | git credential fill
$token = ($cred | Where-Object { $_ -like "password=*" }).Substring(9)
$H = @{
  Authorization          = "Bearer $token"
  Accept                 = "application/vnd.github+json"
  "User-Agent"           = "feiyu-submit"
  "X-GitHub-Api-Version" = "2022-11-28"
}

function Api($method, $url, $body) {
  $p = @{ Uri = $url; Method = $method; Headers = $H; ContentType = "application/json; charset=utf-8" }
  if ($null -ne $body) {
    $p.Body = [System.Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 6 -Compress))
  }
  Invoke-RestMethod @p
}

# 1. fork must exist
try {
  $f = Api "GET" "https://api.github.com/repos/$FORK" $null
  Write-Output "FORK_OK $($f.full_name) default=$($f.default_branch)"
} catch {
  Write-Output "FORK_MISSING"
  throw "fork not ready: $($_.Exception.Message)"
}

# 2. entry content
if (-not (Test-Path $ENTRY)) { throw "entry file missing" }
$yaml = [System.IO.File]::ReadAllText($ENTRY, [System.Text.Encoding]::UTF8)
$bytes = [System.Text.Encoding]::UTF8.GetBytes($yaml)
Write-Output "ENTRY_CHARS $($yaml.Length) BYTES $($bytes.Length)"
if ($bytes.Length -lt 200) { throw "entry looks empty" }

# 3. create branch from fork's main if absent
try {
  $ref = Api "GET" "https://api.github.com/repos/$FORK/git/ref/heads/main" $null
  $mainSha = $ref.object.sha
  Write-Output "MAIN_SHA $mainSha"
} catch {
  throw "cannot read fork main: $($_.Exception.Message)"
}
$branchSha = $null
try {
  $bref = Api "GET" "https://api.github.com/repos/$FORK/git/ref/heads/$BRANCH" $null
  $branchSha = $bref.object.sha
  Write-Output "BRANCH_EXISTS $branchSha"
} catch {
  $created = Api "POST" "https://api.github.com/repos/$FORK/git/refs" @{ ref = "refs/heads/$BRANCH"; sha = $mainSha }
  $branchSha = $created.object.sha
  Write-Output "BRANCH_CREATED $branchSha"
}

# 4. write the entry file on that branch
$put = @{
  message = "Add ${ME}/feiyu-chat-companion"
  content = [Convert]::ToBase64String($bytes)
  branch  = $BRANCH
}
try {
  $existing = Api "GET" "https://api.github.com/repos/$FORK/contents/$FILE`?ref=$BRANCH" $null
  if ($existing -and $existing.sha) {
    $put.sha = $existing.sha
    $put.message = "Update ${ME}/feiyu-chat-companion entry"
    Write-Output "FILE_UPDATE"
  }
} catch {
  Write-Output "FILE_NEW"
}
$r = Api "PUT" "https://api.github.com/repos/$FORK/contents/$FILE" $put
Write-Output "FILE_WRITTEN $($r.content.path) sha=$($r.content.sha)"

# 5. open the PR
$prBody = [System.IO.File]::ReadAllText($BODY, [System.Text.Encoding]::UTF8)
$prArgs = @{
  title = "Add ${ME}/feiyu-chat-companion (ui)"
  head  = "${ME}:${BRANCH}"
  base  = "main"
  body  = $prBody
  draft = $false
}
try {
  $pr = Api "POST" "https://api.github.com/repos/$UP/pulls" $prArgs
  Write-Output "PR_CREATED $($pr.html_url) number=#$($pr.number)"
} catch {
  Write-Output "PR_FAILED $($_.Exception.Message)"
  if ($_.ErrorDetails) {
    $m = $_.ErrorDetails.Message
    if ($m.Length -gt 800) { $m = $m.Substring(0, 800) }
    Write-Output ($m -replace [regex]::Escape($token), "***")
  }
}
