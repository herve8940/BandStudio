param([Parameter(Mandatory=$true)][string]$RequestFile)
$ErrorActionPreference = 'Stop'
$request = Get-Content -LiteralPath $RequestFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($request.language -notin @('fr','en')) { throw 'Unsupported speech language.' }

# OneCore uses installed Windows voices. Never silently speak in another language.
function Await-WinRT($Operation, [Type]$ResultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and
        $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}
$speaker = $null; $stream = $null; $reader = $null
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media,ContentType=WindowsRuntime]
    $null = [Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime]
    $null = [Windows.Media.SpeechSynthesis.SpeechSynthesisStream,Windows.Media,ContentType=WindowsRuntime]
    $voices = @([Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -like ($request.language+'-*') })
    $wanted = $voices | Where-Object { $_.DisplayName -eq $request.voice -or $_.Id -eq $request.voice } | Select-Object -First 1
    if (-not $wanted) {
        $preferred = if ($request.language -eq 'fr') { 'Julie|Hortense|Paul' } else { 'Zira|Hazel|David|George' }
        $wanted = $voices | Where-Object DisplayName -match $preferred | Select-Object -First 1
    }
    if (-not $wanted) { $wanted = $voices | Select-Object -First 1 }
    if (-not $wanted) { throw 'No OneCore voice for this language.' }
    $speaker = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
    $speaker.Voice = $wanted
    $speaker.Options.SpeakingRate = [Math]::Max(0.5,[Math]::Min(2.0,[double]$request.rate/180.0))
    $stream = Await-WinRT ($speaker.SynthesizeTextToStreamAsync([string]$request.text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $reader = [Windows.Storage.Streams.DataReader]::new($stream.GetInputStreamAt(0))
    $null = Await-WinRT ($reader.LoadAsync([uint32]$stream.Size)) ([uint32])
    $bytes = New-Object byte[] ([int]$stream.Size)
    $reader.ReadBytes($bytes)
    [IO.File]::WriteAllBytes([string]$request.output,$bytes)
    Write-Output ('OneCore: '+$wanted.DisplayName+' ['+$wanted.Language+']')
} catch {
    # Older desktop voices are a fallback in the same language only.
    Write-Output ('OneCore unavailable: '+$_.Exception.Message)
    Add-Type -AssemblyName System.Speech
    $fallback = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $voices = @($fallback.GetInstalledVoices() | Where-Object Enabled | ForEach-Object VoiceInfo | Where-Object { $_.Culture.TwoLetterISOLanguageName -eq $request.language })
        $wanted = $voices | Where-Object Name -eq $request.voice | Select-Object -First 1
        if (-not $wanted) { $wanted = $voices | Select-Object -First 1 }
        if (-not $wanted) { throw ('Voix '+$request.language+' absente. Ouvre Reglages > Voix Windows et ajoute Francais ou Anglais dans Gerer les voix, puis relance la preparation.') }
        $fallback.SelectVoice($wanted.Name)
        $fallback.Rate = [Math]::Max(-5,[Math]::Min(5,[int](($request.rate-180)/30)))
        $fallback.SetOutputToWaveFile([string]$request.output)
        $fallback.Speak([string]$request.text)
        Write-Output ('SAPI: '+$wanted.Name+' ['+$wanted.Culture.Name+']')
    } finally { $fallback.Dispose() }
} finally {
    if ($reader) { $reader.Dispose() }
    if ($stream) { $stream.Dispose() }
    if ($speaker) { $speaker.Dispose() }
}
