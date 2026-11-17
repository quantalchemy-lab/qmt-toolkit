@echo off
setlocal
rem ============================================================
rem  给大QMT内置 Python 3.6（64位）安装 debugpy 1.5.1
rem  用法：在已激活 py36 环境的命令行里执行
rem        安装debugpy.bat "D:\ProgramFiles\你的QMT安装目录"
rem  不带参数时使用下面的默认目录，请改成你自己的路径
rem ============================================================
set "QMT_DIR=%~1"
if "%QMT_DIR%"=="" set "QMT_DIR=D:\ProgramFiles\国金证券QMT交易端"
set "TARGET=%QMT_DIR%\bin.x64\Lib\site-packages"

if not exist "%QMT_DIR%\bin.x64\python36.dll" (
    echo [错误] 未找到 "%QMT_DIR%\bin.x64\python36.dll"
    echo        请确认 QMT 安装目录，或该客户端内置的不是 Python 3.6
    exit /b 1
)
if not exist "%TARGET%" mkdir "%TARGET%"

echo [安装] debugpy 1.5.1 -^> "%TARGET%"
python -m pip install debugpy==1.5.1 --upgrade --target "%TARGET%" --python-version 3.6 --platform win_amd64 --implementation cp --abi cp36m --only-binary=:all: --no-deps -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [错误] 安装失败，请查看上面的 pip 报错
    exit /b 1
)

if exist "%TARGET%\debugpy-1.5.1.dist-info" (
    echo [完成] debugpy 1.5.1 已安装到 "%TARGET%"
    echo        请重启 QMT 客户端后再运行启动器
) else (
    echo [错误] 未找到 debugpy-1.5.1.dist-info，安装可能未成功
    exit /b 1
)
endlocal