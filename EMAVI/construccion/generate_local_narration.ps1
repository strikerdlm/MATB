$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Add-Type -AssemblyName System.Speech
$synth=New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice('Microsoft Sabina Desktop')
$synth.Rate=0
Register-ObjectEvent -InputObject $synth -EventName SpeakProgress -SourceIdentifier EMAVINarration | Out-Null
$audioDir="$repo/EMAVI/video/audio"
New-Item -ItemType Directory -Force -Path $audioDir | Out-Null
try{
 foreach($chapter in (Get-Content "$repo/EMAVI/video/guion.json" -Raw -Encoding utf8 | ConvertFrom-Json)){
  $wav=Join-Path $audioDir ($chapter.id+'.wav')
  $synth.SetOutputToWaveFile($wav)
  $synth.Speak($chapter.text)
  $synth.SetOutputToNull()
  # Verified on this Windows/Sabina installation: SpeakProgress uses a 16 kHz
  # event clock while SetOutputToWaveFile emits 22050 Hz PCM. Normalize it.
  $boundaries=@(Get-Event -SourceIdentifier EMAVINarration | ForEach-Object { @{start_ms=$_.SourceEventArgs.AudioPosition.TotalMilliseconds*16000/22050;sapi_audio_position_ms=$_.SourceEventArgs.AudioPosition.TotalMilliseconds;event_clock_hz=16000;wav_sample_rate=22050;position=$_.SourceEventArgs.CharacterPosition;length=$_.SourceEventArgs.CharacterCount;text=$_.SourceEventArgs.Text} })
  $boundaries | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $audioDir ($chapter.id+'.timing.json')) -Encoding utf8
  Get-Event -SourceIdentifier EMAVINarration | Remove-Event
  Write-Output $chapter.id
 }
} finally {Unregister-Event -SourceIdentifier EMAVINarration; $synth.Dispose()}
