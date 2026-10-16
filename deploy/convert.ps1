param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$InputFile,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MarkerArgs
)

$deployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $deployDir

$containerInput = "/inputs/" + [System.IO.Path]::GetFileName($InputFile)
docker compose -f docker-compose.yml --profile cli run --rm marker $containerInput --output_dir /outputs @MarkerArgs

