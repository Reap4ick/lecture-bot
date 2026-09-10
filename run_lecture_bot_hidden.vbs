Option Explicit

Dim shell, fso, folder
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder

' Run the Flask server with no visible console window.
shell.Run "cmd /c python app.py", 0, False

' Give Flask a moment to start, then open the local site.
WScript.Sleep 3000
shell.Run "http://127.0.0.1:5000", 1, False

Set fso = Nothing
Set shell = Nothing
