"""Animate each Shulka shot with an image-to-video model on fal.ai, then cut the reel.

Needs FAL_KEY in the environment.
    python3 shulka/generate.py            # generate missing clips + assemble
    python3 shulka/generate.py 4-friends  # regenerate one shot, then assemble
    python3 shulka/generate.py --assemble # only cut the reel from clips/ (no FAL_KEY needed)
"""
import base64, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
MODEL = os.environ.get("FAL_MODEL", "fal-ai/kling-video/v2.1/standard/image-to-video")
CLIPS = ROOT / "clips"
OUT = ROOT.parent / "shulka-reel-live.mp4"

# (start, seconds) of each 5s clip to use, and 9:16 crop pan (start, end) as 0..1 of spare width
EDIT = {
    "1-ballot": (0, 3.0, 0.15, 0.10), "2-espresso": (0, 3.0, 0.5, 0.5),
    "3-food": (0.3, 4.7, 0.05, 0.2), "3b-drizzle": (0, 2.5, 0.5, 0.45),
    "4-friends": (0.5, 4.0, 0.0, 1.0), "5-cart": (0.5, 3.5, 0.3, 0.45),
    "6-seating": (0.5, 3.5, 1.0, 0.6), "7-toast": (0, 5.0, 0.7, 0.7),
}
# shots that fall back to a slow handheld push-in on the still when no clip exists
STILL_FALLBACK = {"1-ballot", "2-espresso"}
AMBIENCE = "6-seating"


def call(url, data=None, method=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(data).encode() if data else None,
                                 headers={"Authorization": f"Key {os.environ['FAL_KEY']}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def generate(shot, cfg):
    img = (ROOT / "frames" / f"{shot['frame']}.png").read_bytes()
    job = call(f"https://queue.fal.run/{MODEL}", {
        "prompt": f"{shot['prompt']} {cfg['common']}",
        "negative_prompt": cfg["negative"],
        "image_url": "data:image/png;base64," + base64.b64encode(img).decode(),
        "duration": "5",
    })
    print(f"{shot['frame']}: queued {job['request_id']}", flush=True)
    while (st := call(job["status_url"]))["status"] != "COMPLETED":
        time.sleep(10)
    video = call(job["response_url"])["video"]["url"]
    urllib.request.urlretrieve(video, CLIPS / f"{shot['frame']}.mp4")
    print(f"{shot['frame']}: done", flush=True)


def assemble(cfg):
    names = [s["frame"] for s in cfg["shots"]
             if (CLIPS / f"{s['frame']}.mp4").exists() or s["frame"] in STILL_FALLBACK]
    inputs, parts, labels = [], [], ""
    amb = len(names)  # extra input index for ambience under still shots
    for i, name in enumerate(names):
        t0, dur, a, b = EDIT[name]
        clip = CLIPS / f"{name}.mp4"
        if clip.exists():
            inputs += ["-i", str(clip)]
            src, aud = f"[{i}:v]trim={t0}:{t0 + dur},setpts=PTS-STARTPTS,fps=30,", \
                f"[{i}:a]atrim={t0}:{t0 + dur}"
        else:
            n = int(dur * 30)
            inputs += ["-loop", "1", "-framerate", "30", "-t", str(dur),
                       "-i", str(ROOT / "frames" / f"{name}.png")]
            src = (f"[{i}:v]scale=3200:-1,zoompan=z='1+0.08*on/{n}':d=1:fps=30:s=800x1088:"
                   f"x='iw/2-iw/zoom/2+12*sin(on/23)':y='ih/2-ih/zoom/2+9*sin(on/31+1)',"
                   f"trim=end_frame={n},setpts=PTS-STARTPTS,")
            aud = f"[{amb}:a]atrim={i * dur}:{(i + 1) * dur},volume=0.5"
        parts.append(f"{src}scale=-2:1920:flags=lanczos,"
                     f"crop=1080:1920:x='(iw-ow)*({a}+({b}-{a})*t/{dur})':y=0,setsar=1[v{i}]")
        parts.append(f"{aud},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,"
                     f"afade=in:d=0.05,afade=out:st={dur - 0.08}:d=0.08[a{i}]")
        labels += f"[v{i}][a{i}]"
    inputs += ["-i", str(CLIPS / f"{AMBIENCE}.mp4")]
    graph = ";".join(parts) + f";{labels}concat=n={len(names)}:v=1:a=1[vc][ac];" \
        "[vc]noise=alls=3:allf=t,format=yuv420p[v];[ac]loudnorm=I=-18:TP=-2[a]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs,
                    "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "21",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                    "-movflags", "+faststart", str(OUT)], check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    cfg = json.loads((ROOT / "shots.json").read_text())
    CLIPS.mkdir(exist_ok=True)
    redo = set(sys.argv[1:])
    if "--assemble" not in redo:
        for shot in cfg["shots"]:
            if shot["frame"] in redo or not (CLIPS / f"{shot['frame']}.mp4").exists():
                generate(shot, cfg)
    assemble(cfg)
