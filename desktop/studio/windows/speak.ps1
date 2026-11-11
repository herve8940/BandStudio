param([Parameter(Mandatory=$true)][string]$RequestFile)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$request = Get-Content -LiteralPath $RequestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voices = @($speaker.GetInstalledVoices() | Where-Object Enabled | ForEach-Object VoiceInfo)
    $wanted = $voices | Where-Object Name -eq $request.voice | Select-Object -First 1
    if (-not $wanted) { $wanted = $voices | Where-Object { $_.Culture.TwoLetterISOLanguageName -eq $request.language } | Select-Object -First 1 }
    if (-not $wanted) { $wanted = $voices | Select-Object -First 1 }
    if (-not $wanted) { throw 'Aucune voix Windows installée.' }
    $speaker.SelectVoice($wanted.Name)
    $speaker.Rate = [Math]::Max(-5, [Math]::Min(8, [int](($request.rate - 180) / 30)))
    $speaker.SetOutputToWaveFile($request.output)
    $speaker.Speak([string]$request.text)
} finally { $speaker.Dispose() }
