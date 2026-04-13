Set objShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
objShell.Run "py.exe -w """ & strPath & "\hebrew-dictate.pyw""", 0, False
