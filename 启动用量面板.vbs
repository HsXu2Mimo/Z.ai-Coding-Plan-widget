' Z.ai usage panel launcher: ensure local server is running, then open the panel
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run "pythonw """ & dir & "\proxy.py""", 0, False
WScript.Sleep 1500
sh.Run "cmd /c start """" ""http://127.0.0.1:8788/?live=1""", 0, False
