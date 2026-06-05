$ErrorActionPreference = 'Stop'
$serverDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $serverDir
$target = Join-Path $rootDir 'Archive\ui_legacy\server\release_gate.ps1'
if (!(Test-Path $target)) { throw "Archived script missing: $target" }
& $target @args

