# PowerShell script to update all API URLs from port 8000 to 8001
$files = @(
    "src\api\api.js",
    "src\api\axiosInstance.jsx",
    "src\components\dashboard\Result table.jsx",
    "src\pages\admin\AdminDashboard.jsx",
    "src\pages\admin\Users.jsx",
    "src\pages\subscriber\SubscriberLogin.jsx",
    "src\pages\subscriber\SubscriberSubscribe.jsx",
    "src\pages\ui\BuyCredit.jsx",
    "src\pages\ui\CreditHistory.jsx",
    "src\pages\ui\CreditsContext.jsx",
    "src\pages\ui\Pricing.jsx"
)

foreach ($file in $files) {
    $fullPath = Join-Path $PSScriptRoot $file
    if (Test-Path $fullPath) {
        $content = Get-Content $fullPath -Raw
        $newContent = $content -replace 'http://127\.0\.0\.1:8000', 'http://127.0.0.1:8001'
        Set-Content -Path $fullPath -Value $newContent -NoNewline
        Write-Host "Updated: $file"
    } else {
        Write-Host "File not found: $file" -ForegroundColor Yellow
    }
}

Write-Host "`nAll files updated successfully!" -ForegroundColor Green
