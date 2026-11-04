# Assemble the DressMe technical demo from the screen recordings. Re-run it after re-recording a part.
#   .\demo\build_demo.ps1                 -> demo\DressMe_demo_technique.mp4
# Cut points (seconds) were found by looking at the recordings frame by frame; edit them below if a recording changes.
param(
    [string]$Recordings = "$env:LOCALAPPDATA\Packages\Microsoft.ScreenSketch_8wekyb3d8bbwe\TempState\Recordings",
    [string]$Avatar = "20261104-1730-19.3429393.mp4",     # My 3D Avatar (7 s)
    [string]$Tour   = "20261104-1734-13.3528391.mp4",     # long tour (6 min 54 s)
    [string]$Pack   = "20261104-1747-32.2822537.mp4",     # Help Me Pack, re-recorded (1 min 14 s)
    [string]$Out    = (Join-Path $PSScriptRoot "DressMe_demo_technique.mp4")
)
$ErrorActionPreference = "Stop"

$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    $ffmpeg = & python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
}
if (-not (Test-Path $ffmpeg)) { throw "ffmpeg not found (pip install imageio-ffmpeg, or install ffmpeg)." }

# Order of the demo: wardrobe -> avatar -> outfit builder / try-on / stylist -> Help Me Pack (new) -> shop tools.
#   removed from the tour: the old Help Me Pack part (187.4 s - 237.95 s), and the wardrobe screen at the end of
#   "Should I Buy?" (from 407.4 s) where the boots were badly cut out.
$segments = @(
    @{ File = $Tour;   Start = 0;       End = 123.9  },   # dashboard, wardrobe, search
    @{ File = $Avatar; Start = 0;       End = 7.34   },   # 3D avatar
    @{ File = $Tour;   Start = 124.4;   End = 187.4  },   # outfit builder, virtual try-on, AI stylist
    @{ File = $Pack;   Start = 0;       End = 73.88  },   # Help Me Pack
    @{ File = $Tour;   Start = 237.95;  End = 407.4  }    # Wardrobe Gaps, Find Similar, Should I Buy?
)
$fade = 0.25         # seconds of fade at each cut (through black)
$width = 1920; $height = 912
$work = Join-Path $env:TEMP "dressme_demo_parts"
New-Item -ItemType Directory -Force $work | Out-Null

# One small encode per part (low memory: the recordings are huge), then a lossless join.
$list = @()
$total = 0
for ($i = 0; $i -lt $segments.Count; $i++) {
    $s = $segments[$i]
    $duration = [Math]::Round($s.End - $s.Start, 3)
    $total += $duration
    $part = Join-Path $work ("part{0}.mp4" -f $i)
    $filter = "scale={0}:{1},fps=30,format=yuv420p,setsar=1,fade=t=in:st=0:d={2},fade=t=out:st={3}:d={2}" -f $width, $height, $fade, ($duration - $fade)
    Write-Host ("Part {0}/{1}: {2} [{3} s]" -f ($i + 1), $segments.Count, $s.File, $duration)
    # Low-memory settings: this computer often has little free memory. -preset veryfast, a short lookahead and one
    # thread keep ffmpeg under about 300 MB.
    & $ffmpeg -hide_banner -loglevel error -y -threads 1 -ss $s.Start -t $duration -i (Join-Path $Recordings $s.File) `
        -vf $filter -an -c:v libx264 -preset veryfast -crf 21 -threads 1 -x264-params "rc-lookahead=5:ref=1:bframes=1" `
        -pix_fmt yuv420p $part
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed on part $i" }
    $list += ("file '{0}'" -f $part.Replace([string][char]92, "/"))
}
$listFile = Join-Path $work "parts.txt"
Set-Content -Path $listFile -Value $list -Encoding ASCII
Write-Host ("Joining {0} parts (about {1:N0} s) -> {2}" -f $segments.Count, $total, $Out)
& $ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $listFile -c copy -movflags +faststart $Out
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed while joining" }
Write-Host "Done: $Out"
