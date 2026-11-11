$ErrorActionPreference = 'Stop'

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
  throw 'Flutter is not installed or is not available on PATH. Install Flutter 3.24+ and retry.'
}

$mobileRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $mobileRoot
try {
  flutter create . --platforms android,ios --org in.carbonx --project-name carbonx_mobile
  flutter pub get
  dart format lib test
  flutter analyze
  flutter test
} finally {
  Pop-Location
}
