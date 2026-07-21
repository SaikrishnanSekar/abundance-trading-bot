If WScript.Arguments.Count = 0 Then WScript.Quit 1
Set shellObj = CreateObject("WScript.Shell")
shellObj.Run WScript.Arguments(0), 0, True
