$ErrorActionPreference = 'Stop'

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
  throw 'Flutter is not installed or is not available on PATH. Install Flutter 3.44.0 and retry.'
}

$mobileRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $mobileRoot
try {
  flutter pub get --enforce-lockfile
  if ($LASTEXITCODE) { throw 'Flutter dependency installation failed.' }
  flutter analyze
  if ($LASTEXITCODE) { throw 'Flutter analysis failed.' }
  flutter test
  if ($LASTEXITCODE) { throw 'Flutter tests failed.' }
} finally {
  Pop-Location
}
