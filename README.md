# To-do list

Windows 桌面待办工具，支持截止时间、备注、完成历史、CSV 导出、窗口置顶和托盘运行。

从 Releases 下载 Windows x64 MSI 安装包，运行向导并选择安装目录。安装完成后从开始菜单打开。齿轮菜单可以选择开机自启，或者查看和更改事项保存位置。

新安装的事项默认保存到 `%APPDATA%\To-do list\tasks.sqlite3`。已设置的保存位置由 `preferences.json` 记录，由源代码版和安装版共用。若旧版正在运行，请从托盘退出后再打开安装版。卸载程序会保留事项数据库。

## 本地构建

在 Windows x64 上使用 Python 3.14 和 .NET SDK。安装 WiX 6 后构建。

```powershell
python -m pip install -r requirements-build.txt
dotnet tool install --global wix --version 6.0.2
wix extension add --global WixToolset.UI.wixext/6.0.2
.\build.ps1
```

安装包生成在 `dist\`。开发时可以运行 `python Todo.pyw`。
