# Install the Store package on a real Windows machine and check that it works.
#
# Runs on a GitHub Windows runner (windows-smoke.yml), or on your own PC from an
# admin PowerShell after `python scripts/build_desktop.py`. It:
#   1. makes a throwaway code-signing certificate and trusts it,
#   2. builds and signs the MSIX with it, installs it with Add-AppxPackage,
#   3. starts the installed app through its `noscam` alias, headless, with the demo,
#   4. checks the service, the phone app, the demo sites, a scam payment being held,
#      an ordinary payment going through, Store detection and where data is kept,
#   5. leaves the signed package and the certificate in dist\ for a person to
#      install by hand.
# Anything that fails is printed as FAIL and the script exits non-zero.

$ErrorActionPreference = "Stop"
$results = [System.Collections.Generic.List[string]]::new()
$failed = 0
function Check($name, [scriptblock]$test) {
    try {
        $detail = & $test
        $script:results.Add("PASS  $name  $detail")
    } catch {
        $script:results.Add("FAIL  $name  $($_.Exception.Message)")
        $script:failed++
    }
}

# --- 1. test certificate (subject must equal the manifest's Publisher) -------
$publisher = if ($env:MSIX_PUBLISHER) { $env:MSIX_PUBLISHER } else { "CN=NoScamLocalTest" }
$cert = New-SelfSignedCertificate -Type Custom -Subject $publisher -KeyUsage DigitalSignature `
    -FriendlyName "NoScam test signing" -CertStoreLocation "Cert:\CurrentUser\My" `
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
$pfxPassword = ConvertTo-SecureString -String "noscam-test" -Force -AsPlainText
New-Item -ItemType Directory -Force dist | Out-Null
Export-PfxCertificate -Cert $cert -FilePath dist\noscam-test.pfx -Password $pfxPassword | Out-Null
Export-Certificate -Cert $cert -FilePath dist\NoScam-test-certificate.cer | Out-Null
Import-Certificate -FilePath dist\NoScam-test-certificate.cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null

# --- 2. build, sign, install ---------------------------------------------------
$env:MSIX_PFX = "dist\noscam-test.pfx"
$env:MSIX_PFX_PASSWORD = "noscam-test"
python scripts\build_msix.py
if ($LASTEXITCODE -ne 0) { throw "build_msix.py failed" }
$msix = Get-ChildItem dist\NoScam-*-x64.msix | Select-Object -First 1

Check "package installs" {
    Add-AppxPackage -Path $msix.FullName
    $pkg = Get-AppxPackage | Where-Object { $_.Name -like "*NoScam*" } | Select-Object -First 1
    if (-not $pkg) { throw "not listed by Get-AppxPackage" }
    $script:pkg = $pkg
    "$($pkg.PackageFullName)"
}

Check "manifest registers the startup task and alias" {
    $m = Get-AppxPackageManifest -Package $script:pkg.PackageFullName
    $xml = $m.OuterXml
    if ($xml -notmatch "windows.startupTask") { throw "no startup task" }
    if ($xml -notmatch "noscam.exe") { throw "no execution alias" }
    "startup task + alias present"
}

# --- 3. start it through the alias --------------------------------------------
$alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\noscam.exe"
Check "noscam alias exists" {
    if (-not (Test-Path $alias)) { throw "missing $alias" }
    $alias
}
$proc = Start-Process -FilePath $alias -ArgumentList "--headless", "--no-open", "--demo" -PassThru
$up = $false
foreach ($i in 1..60) {
    try { Invoke-RestMethod http://127.0.0.1:8787/health -TimeoutSec 2 | Out-Null; $up = $true; break }
    catch { Start-Sleep -Seconds 1 }
}

Check "service starts and answers /health" {
    if (-not $up) { throw "no answer on 127.0.0.1:8787 within 60s" }
    $h = Invoke-RestMethod http://127.0.0.1:8787/health
    "version $($h.version)"
}

Check "knows it is a Store install (GitHub update check off)" {
    $v = Invoke-RestMethod http://127.0.0.1:8787/version
    if ($v.checking -ne $false) { throw "update check is on: is_store_package() returned False" }
    "checking=$($v.checking)"
}

Check "phone app is served" {
    $r = Invoke-WebRequest http://127.0.0.1:8787/app/ -UseBasicParsing
    if ($r.StatusCode -ne 200 -or $r.Content -notmatch "NoScam") { throw "status $($r.StatusCode)" }
    "200, $($r.Content.Length) bytes"
}

Check "demo messenger and bank are served" {
    $a = (Invoke-WebRequest http://127.0.0.1:8790/ -UseBasicParsing).StatusCode
    $b = (Invoke-WebRequest http://127.0.0.1:8791/ -UseBasicParsing).StatusCode
    $c = (Invoke-WebRequest http://127.0.0.1:8792/content.js -UseBasicParsing).StatusCode
    if ($a -ne 200 -or $b -ne 200 -or $c -ne 200) { throw "$a $b $c" }
    "8790 $a, 8791 $b, content.js $c"
}

$now = (Get-Date).ToUniversalTime().AddSeconds(-30).ToString("o")
Check "scam payment from a WhatsApp link is held" {
    $body = @{
        action = @{ type = "payment"; host = "hdfc-secure.example"; amount = 18000; payee = "Rahul Verma" }
        provenance = @{ origin = "link"; source_host = "web.whatsapp.com"; at = $now }
    } | ConvertTo-Json -Depth 4
    $d = Invoke-RestMethod http://127.0.0.1:8787/gate/check -Method Post -Body $body -ContentType "application/json"
    if ($d.disposition -eq "allow") { throw "allowed: $($d.reason_code)" }
    "$($d.disposition) / $($d.reason_code)"
}

Check "ordinary payment to a known payee goes through" {
    $body = @{
        action = @{ type = "payment"; host = "mybank.example"; amount = 2000; payee = "Landlord" }
        provenance = @{ origin = "typed"; at = $now }
    } | ConvertTo-Json -Depth 4
    $d = Invoke-RestMethod http://127.0.0.1:8787/gate/check -Method Post -Body $body -ContentType "application/json"
    if ($d.disposition -ne "allow") { throw "$($d.disposition): $($d.reason_code)" }
    "allow"
}

Check "a web page cannot change settings" {
    try {
        Invoke-RestMethod http://127.0.0.1:8787/limits -Method Put -Body "{}" -ContentType "application/json" `
            -Headers @{ Origin = "https://scam.example" } | Out-Null
        throw "accepted a request from a web page"
    } catch [System.Net.WebException] {
        "refused ($([int]$_.Exception.Response.StatusCode))"
    } catch {
        if ($_.Exception.Message -match "403") { "refused (403)" } else { throw }
    }
}

Check "audit log chain verifies" {
    $a = Invoke-RestMethod http://127.0.0.1:8787/audit/verify
    if (-not $a.ok) { throw "broken at line $($a.first_broken_line)" }
    "$($a.records) records"
}

Check "household data is kept inside the package's folder" {
    $base = Join-Path $env:LOCALAPPDATA "Packages\$($script:pkg.PackageFamilyName)"
    $found = Get-ChildItem $base -Recurse -Filter household.json -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) { throw "no household.json under $base" }
    $found.FullName.Replace($env:LOCALAPPDATA, "%LOCALAPPDATA%")
}

Check "a second launch exits cleanly instead of failing on the busy port" {
    $p2 = Start-Process -FilePath $alias -ArgumentList "--headless", "--no-open" -PassThru
    if (-not $p2.WaitForExit(20000)) { $p2.Kill(); throw "second copy kept running" }
    "exit code $($p2.ExitCode)"
}

# --- 4. clean up --------------------------------------------------------------
Get-Process -Name NoScam -ErrorAction SilentlyContinue | Stop-Process -Force
Check "uninstalls cleanly" {
    Remove-AppxPackage -Package $script:pkg.PackageFullName
    if (Get-AppxPackage | Where-Object { $_.Name -like "*NoScam*" }) { throw "still installed" }
    "removed"
}
Remove-Item dist\noscam-test.pfx -ErrorAction SilentlyContinue   # never ship the private key

"`n==== NoScam on Windows: smoke test ===="
$results | ForEach-Object { $_ }
"======================================"
$results | Out-File -Encoding utf8 dist\smoke-results.txt
if ($failed -gt 0) { exit 1 }
