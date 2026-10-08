@echo off
title Deploy Optimization Solver to GCP (Project: ve-grp-1-078-ed-tech-02-qwv9)
cd /d "c:\Users\jinnie.ong\OneDrive - Nanyang Technological University\NTU DATA\NTU Works\Antigravity_Folder\BT2404"

set "GCLOUD=C:\Users\jinnie.ong\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
if not exist "%GCLOUD%" set "GCLOUD=gcloud"

echo ======================================================================
echo   Optimization Solver - Google Cloud Run Deployment
echo   Target GCP Project : ve-grp-1-078-ed-tech-02-qwv9
echo   Target Region      : asia-southeast1 (Singapore)
echo ======================================================================
echo.

echo [Step 1/3] Setting GCP project and quota project...
call "%GCLOUD%" config set project ve-grp-1-078-ed-tech-02-qwv9
call "%GCLOUD%" auth application-default set-quota-project ve-grp-1-078-ed-tech-02-qwv9

echo.
echo [Step 2/3] Building and Deploying to Google Cloud Run...
echo (Building container with COIN-OR CBC solver via Cloud Build)
echo.

call "%GCLOUD%" run deploy optimization-solver ^
  --source . ^
  --platform managed ^
  --region asia-southeast1 ^
  --allow-unauthenticated ^
  --project ve-grp-1-078-ed-tech-02-qwv9

if errorlevel 1 (
    echo.
    echo ======================================================================
    echo [ERROR] Cloud Run deployment encountered an error.
    echo Check the error message above for details.
    echo ======================================================================
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   SUCCESS! Deployment complete.
echo ======================================================================
echo Live Service URL:
call "%GCLOUD%" run services describe optimization-solver --platform managed --region asia-southeast1 --project ve-grp-1-078-ed-tech-02-qwv9 --format="value(status.url)"
echo ======================================================================
echo.
pause
