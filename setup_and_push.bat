@echo off
echo ========================================
echo Setting up Git and Pushing to GitHub
echo ========================================

cd c:\Users\SMART TECH HUB\Desktop\xauusd_scalper\skybot

echo.
echo Initializing Git repository...
git init

echo.
echo Adding all files...
git add .

echo.
echo Committing files...
git commit -m "Initial commit: AI Trading Bot with CI/CD pipeline"

echo.
echo Adding remote origin...
git remote add origin https://github.com/Stanza369/skybot.git

echo.
echo Pushing to GitHub...
git push -u origin main

echo.
echo ========================================
echo Done! Check your GitHub repository.
echo https://github.com/Stanza369/skybot
echo ========================================
pause