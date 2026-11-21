param(
    [string] $Python = 'python',
    [string] $Iscc = 'ISCC.exe'
)

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $icon = Join-Path $PSScriptRoot "one-piece.ico"
    $mascot = Join-Path $PSScriptRoot "zoro.png"
    $entry = Join-Path $PSScriptRoot "Todo.pyw"
    & $Python -m PyInstaller --noconfirm --onedir --windowed --name 'To-do list' `
        --distpath 'build\app' --workpath 'build\work' --specpath 'build' `
        --icon $icon --add-data "${icon}:." --add-data "${mascot}:." $entry
    if ($LASTEXITCODE -ne 0) { throw 'Application packaging failed.' }

    & $Iscc 'installer.iss'
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
}
finally {
    Pop-Location
}
