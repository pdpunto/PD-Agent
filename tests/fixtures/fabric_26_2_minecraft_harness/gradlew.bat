@echo off
call "%~dp0..\l11_minecraft_harness\gradlew.bat" -p "%~dp0" %*
exit /b %ERRORLEVEL%
