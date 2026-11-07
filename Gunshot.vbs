' Double-click to start Gunshot from source (no console window).
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & here & "\.venv\Scripts\pythonw.exe"" -m gunshot", 0, False
