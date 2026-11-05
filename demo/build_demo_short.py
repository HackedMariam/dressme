"""The short demo of DressMe (no voice, fast, 4 minutes at most) with all the features.

    python demo/build_demo_short.py            ->  demo/DressMe_demo_complete.mp4

Parts, in order (speed-ups are in the table below):
  wardrobe + search | 3D avatar | outfit builder + virtual try-on | AI Stylist (NEW recording) |
  Help Me Pack | Wardrobe Gaps + Find Similar | Outfits to buy + shop try-on (NEW) | Should I buy this? (NEW)
The old AI Stylist part (tour 164.5 s - 187.4 s) and the old Should I buy part (tour 334.3 s - 407.4 s) are left out.
Low-memory settings: one small encode per part, then a lossless join.
"""
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import imageio_ffmpeg

REC = Path.home() / "AppData/Local/Packages/Microsoft.ScreenSketch_8wekyb3d8bbwe/TempState/Recordings"
TOUR = REC / "20261104-1734-13.3528391.mp4"       # long tour (6 min 54 s)
AVATAR = REC / "20261104-1730-19.3429393.mp4"     # My 3D Avatar (7 s)
PACK = REC / "20261104-1747-32.2822537.mp4"       # Help Me Pack (1 min 14 s)
STYLIST = REC / "20261105-1658-31.7904798.mp4"    # NEW AI Stylist, the assistant (43 s)
BUY = REC / "20261105-1657-33.9590174.mp4"        # NEW Should I buy this? (15 s)
SHOP = REC / "20261105-1703-30.1997793.mp4"       # NEW outfits to buy + virtual try-on of a shop item (40 s)
OUT = Path(__file__).with_name("DressMe_demo_complete.mp4")

W, H, FADE, LIMIT = 1920, 912, 0.25, 240.0
# (file, start, end, speed, caption)
PARTS = [
    (TOUR, 0.0, 123.9, 2.8, "Dashboard, wardrobe, smart search"),
    (AVATAR, 0.0, 7.34, 1.5, "My 3D avatar"),
    (TOUR, 124.4, 164.5, 2.0, "Outfit Builder and virtual try-on"),
    (STYLIST, 0.0, 43.53, 1.5, "AI Stylist - one assistant, several agents"),
    (PACK, 0.0, 73.88, 2.0, "Help Me Pack"),
    (TOUR, 237.95, 334.3, 2.2, "Wardrobe gaps and Find Similar"),
    (SHOP, 0.0, 6.0, 1.3, "Outfits to buy from Tunisian shops"),
    (SHOP, 6.0, 26.0, 5.0, "Virtual try-on of a shop item on your avatar"),
    (SHOP, 26.0, 39.79, 1.0, "Virtual try-on of a shop item on your avatar"),
    (BUY, 0.0, 14.7, 1.0, "Should I buy this?"),
]


def main() -> int:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    total = sum((end - start) / speed for _, start, end, speed, _ in PARTS)
    print(f"expected length: {total:.1f} s ({total / 60:.2f} min)")
    if total > LIMIT:
        print("too long for the limit; raise the speeds")
        return 1
    work = Path(tempfile.gettempdir()) / "dressme_demo_short"
    work.mkdir(exist_ok=True)
    listing = []
    for index, (source, start, end, speed, caption) in enumerate(PARTS):
        out_duration = (end - start) / speed
        key = zlib.crc32(repr((str(source), start, end, speed, caption)).encode())
        part = work / f"part{index}_{key}.mp4"
        if part.exists() and part.stat().st_size > 0:
            print(f"part {index + 1}/{len(PARTS)}: {caption} (kept)", flush=True)
            listing.append(f"file '{part.as_posix()}'")
            continue
        filters = (f"setpts=PTS/{speed},fps=30,scale={W}:{H}:force_original_aspect_ratio=decrease,"
                   f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
                   f"drawtext=text='{caption}':x=28:y=h-64:fontsize=30:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=12,"
                   f"format=yuv420p,fade=t=in:st=0:d={FADE},fade=t=out:st={out_duration - FADE:.3f}:d={FADE}")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-threads", "1", "-ss", str(start), "-t", f"{end - start:.3f}",
                   "-i", str(source), "-an", "-vf", filters, "-t", f"{out_duration:.3f}", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "24", "-rc-lookahead", "8", "-threads", "1", "-movflags", "+faststart", str(part)]
        print(f"part {index + 1}/{len(PARTS)}: {caption} ({out_duration:.1f} s)", flush=True)
        if subprocess.run(command).returncode != 0:
            print(f"ffmpeg failed on part {index + 1}")
            return 1
        listing.append(f"file '{part.as_posix()}'")
    (work / "list.txt").write_text("\n".join(listing), encoding="utf-8")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
               "-c", "copy", "-movflags", "+faststart", str(OUT)]
    if subprocess.run(command).returncode != 0:
        print("join failed")
        return 1
    print("written", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
