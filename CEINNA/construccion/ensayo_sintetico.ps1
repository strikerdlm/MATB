param([string]$Root='E:\Downloads\MATB\CEINNA')
$ErrorActionPreference='Stop'
$target=Join-Path $Root 'revision\lectura_sintetica'
New-Item -ItemType Directory -Force -Path $target | Out-Null
$data=Get-Content (Join-Path $Root 'guion\notas_data.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$voice=New-Object -ComObject SAPI.SpVoice
$available=$voice.GetVoices('Language=80A')
if($available.Count -eq 0){throw 'No se encontró una voz local de español mexicano.'}
$voice.Voice=$available.Item(0)
$voice.Rate=0
$records=@()
foreach($slide in $data){
    if([string]::IsNullOrWhiteSpace($slide.spoken)){continue}
    $path=Join-Path $target ('slide_{0:00}.wav' -f [int]$slide.slide)
    $stream=New-Object -ComObject SAPI.SpFileStream
    try {
        $stream.Open($path,3,$false)
        $voice.AudioOutputStream=$stream
        $null=$voice.Speak($slide.spoken)
    } finally {$stream.Close()}
    $records+=[PSCustomObject]@{slide=$slide.slide;voice=$voice.Voice.GetDescription();rate=$voice.Rate;allocated_seconds=$slide.seconds;path=$path}
}
$records|ConvertTo-Json -Depth 4|Set-Content (Join-Path $target 'manifest.json') -Encoding UTF8
Write-Output ('Lectura sintética local generada para '+$records.Count+' láminas. No es ensayo humano.')
