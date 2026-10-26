"""Animate each Shulka shot with an image-to-video model on fal.ai, then cut the reel.

Needs FAL_KEY in the environment.
    python3 shulka/generate.py            # generate missing clips + assemble
    python3 shulka/generate.py 4-friends  # regenerate one shot, then assemble
"""
import base64, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
MODEL = os.environ.get("FAL_MODEL", "fal-ai/kling-video/v2.1/standard/image-to-video")
CLIPS = ROOT / "clips"
OUT = ROOT.parent / "shulka-reel-live.mp4"

# seconds of each 5s clip to use, and 9:16 crop pan (start, end) as 0..1 of spare width
EDIT = {
    "1-ballot": (3.0, 0.15, 0.10), "2-espresso": (3.0, 0.5, 0.5),
    "3-food": (3.0, 0.0, 0.6), "3b-drizzle": (2.5, 0.5, 0.45),
    "4-friends": (4.0, 0.0, 1.0), "5-cart": (3.0, 0.3, 0.45),
    "6-seating": (3.0, 1.0, 0.6), "7-toast": (3.5, 0.55, 0.55),
}


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
    inputs, parts = [], []
    for i, shot in enumerate(cfg["shots"]):
        dur, a, b = EDIT[shot["frame"]]
        inputs += ["-i", str(CLIPS / f"{shot['frame']}.mp4")]
        parts.append(f"[{i}:v]trim=0:{dur},setpts=PTS-STARTPTS,fps=30,scale=-2:1920:flags=lanczos,"
                     f"crop=1080:1920:x='(iw-ow)*({a}+({b}-{a})*t/{dur})':y=0,setsar=1[v{i}]")
    n = len(cfg["shots"])
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(n)) + \
        f"concat=n={n}:v=1:a=0,noise=alls=3:allf=t,format=yuv420p[v]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-filter_complex", graph, "-map", "[v]", "-map", f"{n}:a", "-shortest",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-c:a", "aac",
                    "-movflags", "+faststart", str(OUT)], check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    cfg = json.loads((ROOT / "shots.json").read_text())
    CLIPS.mkdir(exist_ok=True)
    redo = set(sys.argv[1:])
    for shot in cfg["shots"]:
        if shot["frame"] in redo or not (CLIPS / f"{shot['frame']}.mp4").exists():
            generate(shot, cfg)
    assemble(cfg)
