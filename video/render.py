"""Export viaje.html to MP4.
Usage: python render.py [--music track.mp3] [--out viaje.mp4] | python render.py --stills 1,8.5,20
Requires: pip install playwright && playwright install chromium; ffmpeg on PATH."""
import sys, pathlib, subprocess, argparse, shutil
from playwright.sync_api import sync_playwright
ap=argparse.ArgumentParser(); ap.add_argument('--stills'); ap.add_argument('--music', default='')
ap.add_argument('--out', default='viaje.mp4'); ap.add_argument('--fps', type=int, default=30)
a=ap.parse_args()
RAF='new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))'
here=pathlib.Path(__file__).resolve().parent
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1920,'height':1080})
    pg.goto((here/'viaje.html').as_uri()+'?render'); pg.wait_for_timeout(500)
    dur=pg.evaluate('DURATION')
    if a.stills:
        for t in a.stills.split(','):
            pg.evaluate(f'render({float(t)})'); pg.evaluate(RAF); pg.screenshot(path=str(here/f'still_{t}.jpg'), type='jpeg', quality=85)
        sys.exit()
    fr=here/'_frames'; shutil.rmtree(fr, ignore_errors=True); fr.mkdir()
    n=int(dur*a.fps)
    for i in range(n):
        pg.evaluate(f'render({i/a.fps})'); pg.evaluate(RAF); pg.screenshot(path=str(fr/f'{i:05d}.jpg'), type='jpeg', quality=92)
        if i % 300 == 0: print(f'{i}/{n}', flush=True)
    b.close()
cmd=['ffmpeg','-y','-loglevel','error','-framerate',str(a.fps),'-i',str(fr/'%05d.jpg')]
if a.music:
    cmd+=['-stream_loop','-1','-i',a.music,'-filter_complex',f'[1:a]atrim=0:{dur},asetpts=PTS-STARTPTS,volume=0.28,afade=t=in:st=0:d=1.5,afade=t=out:st={dur-3}:d=3[a]','-map','0:v','-map','[a]','-c:a','aac','-b:a','160k','-ar','44100']
cmd+=['-c:v','libx264','-profile:v','main','-level','4.1','-pix_fmt','yuv420p','-crf','20','-movflags','+faststart','-shortest',str(here/a.out)]
subprocess.run(cmd, check=True); shutil.rmtree(fr); print('ok', a.out)
