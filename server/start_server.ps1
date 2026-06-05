$ErrorActionPreference = 'Stop'
$serverDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $serverDir
$target = Join-Path $rootDir 'Archive\ui_legacy\server\start_server.ps1'
if (!(Test-Path $target)) { throw "Archived script missing: $target" }
& $target @args

