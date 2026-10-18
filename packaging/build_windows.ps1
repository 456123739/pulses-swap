# Pulses Swap —— Windows 一键打包（在 Windows 10/11 上运行）
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# 产物：
#   dist\PulsesSwap\PulsesSwap.exe              目录版（可直接运行 / 绿色版打包用）
#   dist\installer\PulsesSwap-Setup-<版本>.exe  安装器（装了 Inno Setup 才会出）
#
# 说明：
#   · PyInstaller 不能交叉编译，Windows 的 exe 只能在 Windows 上出
#   · 图标取 packaging\icon.ico（由 make_icon.py 生成），漏了会退回 Tk 羽毛图标
#   · 没装 Inno Setup 也不影响：目录版照样能跑，装好后再跑一次本脚本即可出安装器

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "== 1/4 检查 Python ==" -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) { throw "没找到 python，请先安装 Python 3.10+" }

Write-Host "== 2/4 安装依赖 ==" -ForegroundColor Cyan
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

Write-Host "== 3/4 PyInstaller 打包 ==" -ForegroundColor Cyan
if (-not (Test-Path "packaging\icon.ico")) {
    Write-Host "icon.ico 不存在，重新生成图标…" -ForegroundColor Yellow
    python packaging\make_icon.py
}
pyinstaller packaging\pulses_swap.spec --noconfirm --clean
if (-not (Test-Path "dist\PulsesSwap\PulsesSwap.exe")) { throw "打包失败：没有生成 exe" }

$exe = Get-Item "dist\PulsesSwap\PulsesSwap.exe"
Write-Host ("  exe: {0}  ({1:N1} MB)" -f $exe.FullName, ($exe.Length / 1MB)) -ForegroundColor Green

Write-Host "== 4/4 安装器 ==" -ForegroundColor Cyan
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    $ver = python -c "import re,pathlib;print(re.search(r'VERSION\s*=\s*\"([^\"]+)\"',pathlib.Path('src/pulses/core/paths.py').read_text(encoding='utf-8')).group(1))"
    Write-Host "  版本号: $ver"
    & $iscc "packaging\installer.iss" "/DMyAppVersion=$ver"
    Get-ChildItem "dist\installer\*.exe" | ForEach-Object {
        Write-Host ("  安装器: {0}  ({1:N1} MB)" -f $_.FullName, ($_.Length / 1MB)) -ForegroundColor Green
    }
} else {
    Write-Host "  跳过：没装 Inno Setup 6（https://jrsoftware.org/isdl.php）" -ForegroundColor Yellow
    Write-Host "  目录版已经在 dist\PulsesSwap\ ，可以直接运行" -ForegroundColor Yellow
}

Write-Host "`n完成。" -ForegroundColor Green
