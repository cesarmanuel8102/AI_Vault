PS C:\Windows\system32> Invoke-Brain "Devuelve SOLO JSON." "JSON: dime tu dominio y saluda en 2 palabras"

ERROR BODY:


PS C:\Windows\system32> curl.exe -sS -i -X POST "http://127.0.0.1:8001/v1/chat/completions" ^
HTTP/1.1 422 Unprocessable Entity
date: Sat, 21 Feb 2026 00:15:21 GMT
server: uvicorn
content-length: 82
content-type: application/json

{"detail":[{"type":"missing","loc":["body"],"msg":"Field required","input":null}]}curl: (3) URL rejected: Bad hostname
PS C:\Windows\system32>   -H "Content-Type: application/json" ^
-H : The term '-H' is not recognized as the name of a cmdlet, function, script file, or operable program. Check the
spelling of the name, or if a path was included, verify that the path is correct and try again.
At line:1 char:3
+   -H "Content-Type: application/json" ^
+   ~~
    + CategoryInfo          : ObjectNotFound: (-H:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException

PS C:\Windows\system32>   -H "authorization: Bearer MiClaveUltraSegura" ^
-H : The term '-H' is not recognized as the name of a cmdlet, function, script file, or operable program. Check the
spelling of the name, or if a path was included, verify that the path is correct and try again.
At line:1 char:3
+   -H "authorization: Bearer MiClaveUltraSegura" ^
+   ~~
    + CategoryInfo          : ObjectNotFound: (-H:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException

PS C:\Windows\system32>   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"system\",\"content\":\"Responde solo: OK\"},{\"role\":\"user\",\"content\":\"test\"}],\"stream\":false}"curl.exe -sS -i -X POST "http://127.0.0.1:8001/v1/chat/completions" ^
At line:1 char:5
+   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"syste ...
+     ~
Missing expression after unary operator '--'.
At line:1 char:5
+   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"syste ...
+     ~~~~
Unexpected token 'data' in expression or statement.
At line:1 char:9
+   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"syste ...
+         ~
The Data section is missing its statement block.
At line:1 char:14
+ ...  --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"system ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unexpected token 'model\":\"brain-router\",\"messages\":[{\"role\":\"system\",\"content\":\"Responde' in expression or
statement.
    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException
    + FullyQualifiedErrorId : MissingExpressionAfterOperator

PS C:\Windows\system32>   -H "Content-Type: application/json" ^
-H : The term '-H' is not recognized as the name of a cmdlet, function, script file, or operable program. Check the
spelling of the name, or if a path was included, verify that the path is correct and try again.
At line:1 char:3
+   -H "Content-Type: application/json" ^
+   ~~
    + CategoryInfo          : ObjectNotFound: (-H:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException

PS C:\Windows\system32>   -H "authorization: Bearer MiClaveUltraSegura" ^
-H : The term '-H' is not recognized as the name of a cmdlet, function, script file, or operable program. Check the
spelling of the name, or if a path was included, verify that the path is correct and try again.
At line:1 char:3
+   -H "authorization: Bearer MiClaveUltraSegura" ^
+   ~~
    + CategoryInfo          : ObjectNotFound: (-H:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException

PS C:\Windows\system32>   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"system\",\"content\":\"Devuelve SOLO JSON.\"},{\"role\":\"user\",\"content\":\"JSON: dime tu dominio y saluda en 2 palabras\"}],\"stream\":false}"
At line:1 char:5
+   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"syste ...
+     ~
Missing expression after unary operator '--'.
At line:1 char:5
+   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"syste ...
+     ~~~~
Unexpected token 'data' in expression or statement.
At line:1 char:9
+   --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"syste ...
+         ~
The Data section is missing its statement block.
At line:1 char:14
+ ...  --data "{\"model\":\"brain-router\",\"messages\":[{\"role\":\"system ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unexpected token 'model\":\"brain-router\",\"messages\":[{\"role\":\"system\",\"content\":\"Devuelve' in expression or
statement.
    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException
    + FullyQualifiedErrorId : MissingExpressionAfterOperator

PS C:\Windows\system32> $uri = "http://127.0.0.1:8001/v1/chat/completions"
PS C:\Windows\system32> $headers = @{ authorization = "Bearer MiClaveUltraSegura" }
PS C:\Windows\system32> $body = @{
>>   model = "brain-router"
>>   messages = @(
>>     @{ role="system"; content="Devuelve SOLO JSON." }
>>     @{ role="user"; content="JSON: dime tu dominio y saluda en 2 palabras" }
>>   )
>>   stream = $false
>> } | ConvertTo-Json -Depth 12
PS C:\Windows\system32>
PS C:\Windows\system32> try {
>>   Invoke-WebRequest -UseBasicParsing -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body $body
>> } catch {
>>   "STATUS: $($_.Exception.Response.StatusCode.value__)"
>>   "ERRORDETAILS:"
>>   $_.ErrorDetails.Message
>> }
STATUS: 500
ERRORDETAILS:
{"detail":"EMPTY_ANSWER_FROM_MODEL"}
PS C:\Windows\system32>