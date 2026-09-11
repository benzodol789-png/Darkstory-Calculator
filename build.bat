@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo  Build Darkstory Calculator เป็น .exe
echo ==========================================
echo.

echo [1/4] ตรวจตารางข้อมูลเกม...
py game_data.py
if errorlevel 1 goto :failed
echo.

echo [2/4] ตรวจว่าไฟล์ compile ผ่าน...
py -c "import ast,io; ast.parse(io.open('Darkstory_Calculator.py',encoding='utf-8').read()); print('  OK')"
if errorlevel 1 goto :failed
echo.

echo [3/4] กำลัง build (ใช้เวลาสักครู่)...
py -m PyInstaller --noconfirm --clean Darkstory_Calculator.spec
if errorlevel 1 goto :failed
echo.

echo [4/4] คัดลอกไฟล์ประกอบไปที่ dist\
if not exist "dist\darkstory_config.json" (
    copy /y "darkstory_config.example.json" "dist\darkstory_config.json" >nul
    echo   สร้าง dist\darkstory_config.json แล้ว - อย่าลืมใส่ server_url
) else (
    echo   dist\darkstory_config.json มีอยู่แล้ว ไม่เขียนทับ
)
copy /y "README.md" "dist\README.md" >nul
echo.

echo ==========================================
echo  เสร็จแล้ว: dist\Darkstory_Calculator.exe
echo ==========================================
echo.
echo  ก่อนแจกให้คนอื่น อย่าลืม:
echo    - ใส่ server_url ใน dist\darkstory_config.json
echo    - อย่าแจก darkstory_config.json ที่มี token ของคุณ
echo.
goto :end

:failed
echo.
echo *** Build ไม่สำเร็จ - ดูข้อความด้านบน ***
exit /b 1

:end
pause
