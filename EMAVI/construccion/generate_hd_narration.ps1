param(
  [string]$SpeechCli = "$env:USERPROFILE/.codex/skills/speech/scripts/text_to_speech.py",
  [switch]$Force
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$keyFile = Join-Path $repo '.env.local'
if (-not (Test-Path -LiteralPath $SpeechCli)) { throw 'Install the speech skill or supply -SpeechCli.' }
$previousKey = $env:OPENAI_API_KEY
try {
  $keyLine = [IO.File]::ReadLines($keyFile) | Where-Object { $_ -match '^\s*(?:export\s+)?OPENAI_API_KEY\s*=' } | Select-Object -First 1
  if (-not $keyLine) { throw 'OPENAI_API_KEY is missing from .env.local.' }
  $env:OPENAI_API_KEY = (($keyLine -split '=', 2)[1]).Trim().Trim('"').Trim("'")
  python "$PSScriptRoot/assemble_hd_narration.py" --prepare
  if ($LASTEXITCODE -ne 0) { throw 'Could not prepare narration.' }
  $settings = Get-Content -LiteralPath "$repo/EMAVI/video/narracion.json" -Raw -Encoding UTF8 | ConvertFrom-Json
  $instructionsFile = "$PSScriptRoot/runtime/tts-hd/instructions.txt"
  [IO.File]::WriteAllText($instructionsFile, $settings.instructions, [Text.UTF8Encoding]::new($false))
  $arguments = @($SpeechCli, 'speak-batch', '--input', "$PSScriptRoot/runtime/tts-hd/jobs.jsonl", '--out-dir', "$PSScriptRoot/runtime/tts-hd/sentences", '--model', $settings.model, '--voice', $settings.voice, '--speed', [string]$settings.speed, '--instructions-file', $instructionsFile, '--response-format', 'wav', '--rpm', '40', '--attempts', '1')
  if ($Force) { $arguments += '--force' }
  & python @arguments
  if ($LASTEXITCODE -ne 0) { throw 'OpenAI narration generation failed.' }
  python "$PSScriptRoot/assemble_hd_narration.py"
  if ($LASTEXITCODE -ne 0) { throw 'Audio assembly failed.' }
} finally {
  $env:OPENAI_API_KEY = $previousKey
  $batchFile = Join-Path $PSScriptRoot 'runtime/tts-hd/jobs.jsonl'
  if (Test-Path -LiteralPath $batchFile) {
    try { Remove-Item -LiteralPath $batchFile -ErrorAction Stop }
    catch { Write-Warning 'Narration batch remains in ignored runtime directory; no credentials are stored in it.' }
  }
}
