[CmdletBinding()]
param([ValidateSet('codex','claude','both')][string]$Target,[switch]$Force,[Alias('dry-run')][switch]$DryRun,[switch]$Uninstall)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source=Join-Path $repoRoot 'skill\SKILL.md'
function Fail([string]$m){Write-Error $m; exit 1}
if(-not $Target){Fail 'Missing --target codex|claude|both.'}
if(-not(Test-Path -LiteralPath $source -PathType Leaf)){Fail "Skill source not found: $source"}
$text=Get-Content -LiteralPath $source -Raw
if($text -notmatch '(?m)^name:\s*cite-match\s*$' -or $text -notmatch '(?m)^description:'){Fail 'Skill source metadata is invalid.'}
Write-Output "Detected platform: Windows PowerShell"
Write-Output "CiteMatch repository: $repoRoot"
if(Test-Path (Join-Path $repoRoot 'requirements.txt')){Write-Output 'requirements.txt: PASS'}else{Write-Output 'requirements.txt: MISSING'}
foreach($c in 'python','pandoc','pandoc-crossref'){if(Get-Command $c -ErrorAction SilentlyContinue){Write-Output "Dependency ${c}: PASS"}else{Write-Output "Dependency ${c}: MISSING / MANUAL ACTION"}}
$items=@()
if($Target -in @('codex','both')){$items+=@{Name='Codex';Path=(Join-Path $env:USERPROFILE '.agents\skills\cite-match\SKILL.md')}}
if($Target -in @('claude','both')){Fail 'Claude target cannot be resolved from Windows PowerShell. Run installers/install.sh in Claude Git Bash or WSL.'}
$rendered=$text.Replace('<PROJECT_ROOT>',$repoRoot.Replace('\','/'))
foreach($item in $items){
  $dest=$item.Path; $dir=Split-Path $dest -Parent
  $current=if(Test-Path $dest){Get-Content $dest -Raw}else{$null}
  $same=($null -ne $current -and $current -ceq $rendered)
  $status=if($null -eq $current){'Not installed'}elseif($same){'Already installed'}else{'Update candidate'}
  Write-Output "$($item.Name): $status -> $dest"
  if($DryRun){continue}
  if($Uninstall){
    if($null -eq $current){continue}
    if(-not $same){Fail "Refusing uninstall: $dest is not installer-owned."}
    Remove-Item $dest -Force; Write-Output "$($item.Name): Uninstalled"; continue
  }
  if($same){continue}
  if($status -eq 'Update candidate' -and -not $Force){Write-Output "$($item.Name): Not overwritten (use --force to update).";continue}
  New-Item -ItemType Directory -Force -Path $dir|Out-Null
  if($status -eq 'Update candidate'){Copy-Item $dest "$dest.backup-$(Get-Date -Format yyyyMMddHHmmss)" -Force}
  $tmp="$dest.tmp-$([guid]::NewGuid().ToString('N'))"
  [IO.File]::WriteAllText($tmp,$rendered,[Text.UTF8Encoding]::new($false))
  Move-Item $tmp $dest -Force
  Write-Output "$($item.Name): Installed -> $dest"
}
if(-not $DryRun -and -not $Uninstall){Write-Output 'Use /skills or $cite-match; restart if not discovered.'}
