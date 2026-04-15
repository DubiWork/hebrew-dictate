Set objShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
objShell.Run "C:\Python312\pythonw.exe """ & strPath & "\hebrew-dictate-hotkey.pyw""", 0, False
