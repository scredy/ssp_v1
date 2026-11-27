param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'artifacts'))
if (-not $output.StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw 'Certificate output must stay inside test-harness/artifacts.'
}
New-Item -ItemType Directory -Force -Path $output | Out-Null
$pfxPath = Join-Path $output 'localhost-test.pfx'
$pemPath = Join-Path $output 'localhost-test.pem'
$passwordPath = Join-Path $output 'localhost-test.passphrase'
$passphrase = [Guid]::NewGuid().ToString('N')
$rsa = [System.Security.Cryptography.RSA]::Create(2048)
$request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
  'CN=localhost', $rsa,
  [System.Security.Cryptography.HashAlgorithmName]::SHA256,
  [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
)
$san = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
$san.AddDnsName('localhost')
$san.AddIpAddress([System.Net.IPAddress]::Loopback)
$request.CertificateExtensions.Add($san.Build())
$request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $false))
$request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new([System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment, $false))
$certificate = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5), [DateTimeOffset]::UtcNow.AddDays(1))
[System.IO.File]::WriteAllBytes($pfxPath, $certificate.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx, $passphrase))
$pem = "-----BEGIN CERTIFICATE-----`n$([Convert]::ToBase64String($certificate.RawData, [Base64FormattingOptions]::InsertLineBreaks))`n-----END CERTIFICATE-----`n"
[System.IO.File]::WriteAllText($pemPath, $pem, [System.Text.Encoding]::ASCII)
[System.IO.File]::WriteAllText($passwordPath, $passphrase, [System.Text.Encoding]::ASCII)
Write-Output 'Created an ephemeral localhost TLS certificate in the isolated test run directory.'
