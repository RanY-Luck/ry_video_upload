@echo off
chcp 65001 >nul
echo ========================================
echo 抖音采集快速配置向导
echo ========================================
echo.

echo [步骤1] 测试Cookie有效性
echo.
echo 请先访问 https://www.douyin.com/ 并登录
echo 然后运行Cookie测试工具...
echo.
pause

python test_douyin_cookie.py

echo.
echo ========================================
echo [步骤2] 刷新设备ID
echo ========================================
echo.

python flush_device_id.py

echo.
echo ========================================
echo [步骤3] 修改目标用户URL
echo ========================================
echo.
echo 请编辑 main.py 第72行,填入你要采集的抖音用户主页URL
echo 例如: https://www.douyin.com/user/MS4wLjABAAAA_example
echo.
pause

echo.
echo ========================================
echo [步骤4] 测试采集
echo ========================================
echo.
echo 请输入要测试的抖音用户主页URL:
set /p TEST_URL=

f2 dy -c my_apps.yaml -u %TEST_URL% -m post

echo.
echo ========================================
echo 配置完成!
echo ========================================
echo.
echo 如果测试成功,你可以运行 start.bat 启动自动调度
echo 或者直接运行: python main.py
echo.
pause
