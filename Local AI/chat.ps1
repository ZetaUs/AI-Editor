$Endpoint = "https://editor.zztxer.dpdns.org/api/chat"
$SystemPrompt = "You are a helpful coding assistant."
$MaxHistory = 20

Add-Type -AssemblyName System.Net.Http
Add-Type -AssemblyName System.Windows.Forms

function Convert-MessagesToJson($messages) {
    $parts = @()
    foreach ($m in $messages) {
        $role = $m.role.Replace('\','\\').Replace('"','\"')
        $content = $m.content.Replace('\','\\').Replace('"','\"').Replace("`n","\n")
        $parts += "{`"role`":`"$role`",`"content`":`"$content`"}"
    }
    return "{""messages"":[" + ($parts -join ",") + "],""stream"":true}"
}

function Extract-Text($obj) {
    if ($null -eq $obj) { return "" }
    if ($obj -is [pscustomobject]) {
        if ($obj.PSObject.Properties.Name -contains "response" -and $obj.response -is [string]) {
            return $obj.response
        }
        if ($obj.PSObject.Properties.Name -contains "choices") {
            foreach ($c in $obj.choices) {
                if ($c.PSObject.Properties.Name -contains "delta" -and $c.delta -is [pscustomobject]) {
                    if ($c.delta.PSObject.Properties.Name -contains "content" -and $c.delta.content) {
                        return [string]$c.delta.content
                    }
                }
            }
        }
    }
    return ""
}

function Invoke-AIStream($messages) {
    $jsonBody = Convert-MessagesToJson $messages
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds(60)
    $content = [System.Net.Http.StringContent]::new($jsonBody, [System.Text.Encoding]::UTF8, "application/json")
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $Endpoint)
    $request.Content = $content

    try {
        $response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
        if (-not $response.IsSuccessStatusCode) {
            $reader = New-Object System.IO.StreamReader($response.Content.ReadAsStreamAsync().Result)
            $errBody = $reader.ReadToEnd()
            Write-Host "[HTTP $($response.StatusCode)] $errBody" -ForegroundColor Red
            $reader.Close()
            $response.Dispose()
            $client.Dispose()
            return ""
        }

        $stream = $response.Content.ReadAsStreamAsync().Result
        $reader = New-Object System.IO.StreamReader($stream)
        $full = ""

        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if (-not $line.StartsWith("data:")) { continue }
            $raw = $line.Substring(5).Trim()
            if ($raw -eq "[DONE]") { break }
            try {
                $data = $raw | ConvertFrom-Json
                $text = Extract-Text $data
                if ($text) {
                    $full += $text
                    Write-Host -NoNewline $text
                }
            } catch { }
        }

        $reader.Close()
        $stream.Close()
        $response.Dispose()
        $client.Dispose()
        return $full
    } catch {
        Write-Host "[error] $_" -ForegroundColor Red
        $client.Dispose()
        return ""
    }
}

function Get-ClipboardText {
    try {
        return [System.Windows.Forms.Clipboard]::GetText()
    } catch {
        Write-Host "[clipboard unavailable]" -ForegroundColor Yellow
        return $null
    }
}

Write-Host "=== AI Terminal (PowerShell) ===" -ForegroundColor Cyan
Write-Host "Commands: /quit  /clear  /paste  /help" -ForegroundColor DarkGray
Write-Host ""

$history = @()

while ($true) {
    try {
        $user = Read-Host "> "
    } catch { break }

    $cmd = $user.ToLower().Trim()
    if ($cmd -in @("/quit", "/exit", "/q")) { Write-Host "Bye."; break }
    if ($cmd -eq "/help") { Write-Host "Commands: /quit  /clear  /paste  /help"; continue }
    if ($cmd -eq "/clear") { $history = @(); Write-Host "[history cleared]" -ForegroundColor Yellow; continue }
    if ($cmd -eq "/paste") {
        $user = Get-ClipboardText
        if (-not $user) { Write-Host "[clipboard empty]" -ForegroundColor Yellow; continue }
        Write-Host "-- pasted $($user.Length) chars --" -ForegroundColor DarkGray
        Write-Host $user -ForegroundColor DarkGray
    }

    if (-not $user) { continue }

    $messages = @(
        @{ role = "system"; content = $SystemPrompt }
    ) + $history + @(
        @{ role = "user"; content = $user }
    )

    $full = Invoke-AIStream $messages
    Write-Host ""

    $history += @{ role = "user"; content = $user }
    $history += @{ role = "assistant"; content = $full }
    if ($history.Count -gt $MaxHistory) {
        $history = $history | Select-Object -Last $MaxHistory
    }
}

Write-Host "Session ended." -ForegroundColor DarkGray