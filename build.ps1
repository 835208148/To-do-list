param(
    [string] $Python = 'python',
    [string] $Wix = 'wix',
    [string] $UiExtension = 'WixToolset.UI.wixext'
)

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $icon = Join-Path $PSScriptRoot 'one-piece.ico'
    $mascot = Join-Path $PSScriptRoot 'zoro.png'
    $entry = Join-Path $PSScriptRoot 'Todo.pyw'
    $appArguments = @(
        '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed', '--name', 'To-do list',
        '--distpath', 'build\app', '--workpath', 'build\work', '--specpath', 'build',
        '--icon', $icon, '--add-data', "${icon}:.", '--add-data', "${mascot}:.", $entry
    )
    & $Python @appArguments
    if ($LASTEXITCODE -ne 0) { throw 'Application packaging failed.' }

    $payload = Join-Path $PSScriptRoot 'build\app\To-do list'
    $wixArguments = @(
        'build', '-wx', '-arch', 'x64', '-culture', 'zh-CN', '-ext', $UiExtension,
        '-d', "PayloadPath=$payload", '-o', 'dist\To-do-list-Setup-1.0.0-x64.msi',
        'installer.wxs'
    )
    New-Item -ItemType Directory -Force -Path 'dist' | Out-Null
    if ($Wix.EndsWith('.dll', [StringComparison]::OrdinalIgnoreCase)) {
        & dotnet $Wix @wixArguments
    }
    else {
        & $Wix @wixArguments
    }
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
}
finally {
    Pop-Location
}
