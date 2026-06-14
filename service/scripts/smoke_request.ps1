param(
  [Parameter(Mandatory = $true)]
  [string]$ImagePath,

  [string]$Url = "http://localhost:8081/generate-description",
  [string]$Title = "iPhone 13 128 GB",
  [string]$CategoryName = "Phones",
  [string]$ParamsJson = '{"condition":"used","memory":"128 GB"}'
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Net.Http

$client = New-Object System.Net.Http.HttpClient
$form = New-Object System.Net.Http.MultipartFormDataContent

$form.Add(
  ([System.Net.Http.StringContent]::new($Title, [System.Text.Encoding]::UTF8)),
  "title"
)
$form.Add(
  ([System.Net.Http.StringContent]::new($CategoryName, [System.Text.Encoding]::UTF8)),
  "category_name"
)
$form.Add(
  ([System.Net.Http.StringContent]::new($ParamsJson, [System.Text.Encoding]::UTF8, "application/json")),
  "params"
)

$imageBytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ImagePath))
$imageContent = [System.Net.Http.ByteArrayContent]::new($imageBytes)
$extension = [System.IO.Path]::GetExtension($ImagePath).ToLowerInvariant()
$contentType = switch ($extension) {
  ".jpg" { "image/jpeg" }
  ".jpeg" { "image/jpeg" }
  ".webp" { "image/webp" }
  default { "image/png" }
}
$imageContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse($contentType)
$form.Add($imageContent, "image", [System.IO.Path]::GetFileName($ImagePath))

$response = $client.PostAsync($Url, $form).Result
$body = $response.Content.ReadAsStringAsync().Result
Write-Output $body

if (-not $response.IsSuccessStatusCode) {
  [Environment]::Exit(1)
}
