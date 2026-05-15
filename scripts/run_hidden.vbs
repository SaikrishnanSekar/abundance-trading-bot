If WScript.Arguments.Count = 0 Then WScript.Quit 1
Set wsh = WScript.CreateObject("WScript.Shell")
wsh.Run WScript.Arguments(0), 0, True
