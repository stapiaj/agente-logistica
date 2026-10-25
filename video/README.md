# Explainer video: *El viaje de un retraso*

An animated walk-through of one delayed shipment across every module of the system (on-screen text in Spanish, 99 s). The video is built as an HTML page with motion graphics and exported frame by frame to MP4.

- [`../assets/viaje.mp4`](../assets/viaje.mp4): the exported video.
- [`viaje.html`](viaje.html): the source. Open it in a browser to play it (space = pause, arrows = ±5 s, click = restart).
- [`render.py`](render.py): exports the HTML to MP4 with Playwright + ffmpeg.

## Editing

All editable data sits at the top of `viaje.html` under `EDITABLE DATA`: captions (`CAPTIONS`), speech bubbles (`BUBBLES`), panels (`PANELS`), output chips (`CHIPS`), chapters (`CHAPTERS`), modules (`N`), camera moves (`CAM`) and focus (`FOCUS`). Times are in seconds.

## Exporting

```powershell
pip install playwright
playwright install chromium
python render.py --music path\to\track.mp3      # full video -> viaje.mp4
python render.py --stills 10,20.5                # check single frames
```

## Credits

Music: "Happy Beats / Business Moves Vol. 12" by Sascha Ende ([ende.app](https://ende.app/en)), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
