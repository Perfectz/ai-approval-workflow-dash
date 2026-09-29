param([Parameter(Mandatory=$true)][string]$RequestPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$request = Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $available = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name })
    $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    foreach ($line in $request.lines) {
        if ($available -notcontains $line.voice) { throw "Voice '$($line.voice)' is unavailable. Installed voices: $($available -join ', ')" }
        $synth.SelectVoice($line.voice)
        $synth.Rate = [int]$line.rate
        $synth.Volume = 100
        $synth.SetOutputToWaveFile([string]$line.output, $format)
        $synth.Speak([string]$line.text)
        $synth.SetOutputToNull()
    }
} finally { $synth.Dispose() }
