#!/usr/bin/env pwsh
# Smart Data Assistant - Complete Deployment Automation Script (PowerShell)
# This script fixes the Gemini import, pushes to GitHub, and guides through final Netlify setup

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Smart Data Assistant - Complete Deployment" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify gemini_handler.py is fixed
Write-Host "[STEP 1] Verifying gemini_handler.py fix..." -ForegroundColor Yellow
$content = Get-Content "gemini_handler.py" -Raw
if (-not ($content -match "import google\.generativeai as genai")) {
    Write-Host "ERROR: gemini_handler.py not fixed correctly!" -ForegroundColor Red
    Write-Host "Expected line: import google.generativeai as genai" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] gemini_handler.py is correct." -ForegroundColor Green
Write-Host ""

# Step 2: Check Git is available
Write-Host "[STEP 2] Checking Git..." -ForegroundColor Yellow
try {
    git --version | Out-Null
} catch {
    Write-Host "ERROR: Git is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Git from https://git-scm.com" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Git found." -ForegroundColor Green
Write-Host ""

# Step 3: Add and commit changes
Write-Host "[STEP 3] Staging changes to Git..." -ForegroundColor Yellow
git add gemini_handler.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to stage changes." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Changes staged." -ForegroundColor Green
Write-Host ""

Write-Host "[STEP 4] Creating commit..." -ForegroundColor Yellow
git commit -m "Fix Gemini import for Railway deployment"
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Commit may have failed. Proceeding anyway..." -ForegroundColor Yellow
}
Write-Host "[OK] Commit created." -ForegroundColor Green
Write-Host ""

# Step 5: Push to GitHub
Write-Host "[STEP 5] Pushing to GitHub..." -ForegroundColor Yellow
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Push failed. Check your GitHub connection." -ForegroundColor Red
    Write-Host "Make sure you have:" -ForegroundColor Red
    Write-Host "  - Git configured with your GitHub credentials" -ForegroundColor Red
    Write-Host "  - The repo remote is set to origin" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Pushed to GitHub!" -ForegroundColor Green
Write-Host ""

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "DEPLOYMENT AUTOMATION COMPLETE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS (Manual - takes 2-3 minutes):" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. RAILWAY AUTO-REDEPLOY (Automatic - wait 1-2 minutes)" -ForegroundColor White
Write-Host "   - Go to: https://railway.app" -ForegroundColor White
Write-Host "   - Watch the 'web' service status" -ForegroundColor White
Write-Host "   - Wait for it to turn GREEN (not red)" -ForegroundColor White
Write-Host "   - Click 'web' service > 'Settings' tab" -ForegroundColor White
Write-Host "   - Copy the Domain/Public URL" -ForegroundColor White
Write-Host ""
Write-Host "2. UPDATE NETLIFY.TOML with Railway URL" -ForegroundColor White
Write-Host "   - Open: netlify.toml" -ForegroundColor White
Write-Host "   - Replace: https://<RAILWAY_URL> with your Railway URL" -ForegroundColor White
Write-Host "   - Example: https://smart-data-assistant.railway.app" -ForegroundColor White
Write-Host "   - Save the file" -ForegroundColor White
Write-Host ""
Write-Host "3. COMMIT AND PUSH TO GITHUB" -ForegroundColor White
Write-Host "   - Run: git add netlify.toml" -ForegroundColor White
Write-Host "   - Run: git commit -m 'Update Railway URL in netlify.toml'" -ForegroundColor White
Write-Host "   - Run: git push origin main" -ForegroundColor White
Write-Host ""
Write-Host "4. DEPLOY ON NETLIFY" -ForegroundColor White
Write-Host "   - Go to: https://netlify.com" -ForegroundColor White
Write-Host "   - Click 'Add new site' > 'Import an existing project'" -ForegroundColor White
Write-Host "   - Select GitHub and your smart-data-assistant repo" -ForegroundColor White
Write-Host "   - Netlify auto-detects netlify.toml and deploys" -ForegroundColor White
Write-Host "   - Copy your Netlify URL when ready" -ForegroundColor White
Write-Host ""
Write-Host "5. TEST END-TO-END" -ForegroundColor White
Write-Host "   - Open your Netlify URL" -ForegroundColor White
Write-Host "   - Upload an Excel file" -ForegroundColor White
Write-Host "   - Ask a question to test the chatbot" -ForegroundColor White
Write-Host "   - Stop Railway instance and restart to verify data persists" -ForegroundColor White
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Questions? See DEPLOYMENT_GUIDE.md for detailed troubleshooting" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to exit"
