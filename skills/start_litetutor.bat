@echo off
echo 正在启动 Lite-Tutor...
echo.

:: 启动后端
start "Lite-Tutor Server" cmd /k "cd /d %~dp0 && python server.py"

:: 等待3秒让server启动
timeout /t 3 /nobreak > nul

:: 启动前端
start "Lite-Tutor App" cmd /k "cd /d %~dp0 && streamlit run app.py --server.address 127.0.0.1"

echo 启动完成！浏览器将自动打开。
echo 关闭系统请直接关闭两个终端窗口。
