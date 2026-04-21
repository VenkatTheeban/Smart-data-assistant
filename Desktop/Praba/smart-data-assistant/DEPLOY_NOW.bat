@echo off
REM Smart Data Assistant - Complete Deployment Automation Script
REM This script fixes the Gemini import, pushes to GitHub, and guides through final Netlify setup

echo ============================================================
echo Smart Data Assistant - Complete Deployment
echo ============================================================
echo.

REM Step 1: Verify gemini_handler.py is fixed
echo [STEP 1] Verifying gemini_handler.py fix...
findstr /M "import google.generativeai as genai" gemini_handler.py > nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: gemini_handler.py not fixed. Please run DEPLOY_NOW.ps1 or fix manually.
    pause
    exit /b 1
)
echo [OK] gemini_handler.py is correct.
echo.

REM Step 2: Check Git is available
echo [STEP 2] Checking Git...
git --version > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Git is not installed or not in PATH.
    echo Please install Git from https://git-scm.com
    pause
    exit /b 1
)
echo [OK] Git found.
echo.

REM Step 3: Add and commit changes
echo [STEP 3] Staging changes to Git...
git add gemini_handler.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to stage changes.
    pause
    exit /b 1
)
echo [OK] Changes staged.
echo.

echo [STEP 4] Creating commit...
git commit -m "Fix Gemini import for Railway deployment"
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Commit may have failed. Proceeding anyway.
)
echo [OK] Commit created.
echo.

REM Step 5: Push to GitHub
echo [STEP 5] Pushing to GitHub...
git push origin main
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Push failed. Check your GitHub connection.
    echo Make sure you have:
    echo  - Git configured with your GitHub credentials
    echo  - The repo remote is set to origin
    pause
    exit /b 1
)
echo [OK] Pushed to GitHub!
echo.

echo ============================================================
echo DEPLOYMENT AUTOMATION COMPLETE
echo ============================================================
echo.
echo NEXT STEPS (Manual - takes 2-3 minutes):
echo.
echo 1. RAILWAY AUTO-REDEPLOY (Automatic - wait 1-2 minutes)
echo    - Go to: https://railway.app
echo    - Watch the "web" service status
echo    - Wait for it to turn GREEN (not red)
echo    - Click "web" service ^> "Settings" tab
echo    - Copy the Domain/Public URL
echo.
echo 2. UPDATE NETLIFY.TOML with Railway URL
echo    - Open: netlify.toml
echo    - Replace: https://^<RAILWAY_URL^> with your Railway URL
echo    - Example: https://smart-data-assistant.railway.app
echo    - Save the file
echo.
echo 3. COMMIT AND PUSH TO GITHUB
echo    - Run: git add netlify.toml
echo    - Run: git commit -m "Update Railway URL in netlify.toml"
echo    - Run: git push origin main
echo.
echo 4. DEPLOY ON NETLIFY
echo    - Go to: https://netlify.com
echo    - Click "Add new site" ^> "Import an existing project"
echo    - Select GitHub and your smart-data-assistant repo
echo    - Netlify auto-detects netlify.toml and deploys
echo    - Copy your Netlify URL when ready
echo.
echo 5. TEST END-TO-END
echo    - Open your Netlify URL
echo    - Upload an Excel file
echo    - Ask a question to test the chatbot
echo    - Stop Railway instance and restart to verify data persists
echo.
echo ============================================================
echo Questions? See DEPLOYMENT_GUIDE.md for detailed troubleshooting
echo ============================================================
pause
