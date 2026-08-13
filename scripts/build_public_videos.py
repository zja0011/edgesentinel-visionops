"""Build privacy-reviewed GitHub Release videos from private recordings.

The source recordings and final MP4 files stay outside Git.  Only deterministic
cover frames are written under docs/media/covers.
"""

from __future__ import print_function

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess


PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
COVER_DIR = os.path.join(PROJECT_DIR, "docs", "media", "covers")


PROFILES = (
    {
        "id": "V01",
        "source": "2026-08-12/20260812_V01_end-to-end-dashboard-agent-mcp_take01.mp4",
        "output": "edgesentinel-demo-01-end-to-end-zh-cn-720p.mp4",
        "cover": "demo-01-end-to-end.jpg",
        "cover_second": 130,
        "redactions": ((120, 225, 360, 50),),
    },
    {
        "id": "V02",
        "source": "2026-08-12/20260812_V02_live-vision-people-objects-tracks_take01.mp4",
        "output": "edgesentinel-demo-02-live-vision-zh-cn-720p.mp4",
        "cover": "demo-02-live-vision.jpg",
        "cover_second": 42,
        "redactions": (),
    },
    {
        "id": "V03",
        "source": "2026-08-13/20260813_V03_zone-enter-dwell-exit-track_take01.mp4",
        "output": "edgesentinel-demo-03-zone-events-zh-cn-720p.mp4",
        "cover": "demo-03-zone-events.jpg",
        "cover_second": 72,
        "source_size": (1280, 720),
        # The moving participant remains anonymous while the body, detection
        # box and zone transitions stay visible.
        "redactions": ((220, 95, 360, 215),),
    },
    {
        "id": "V04",
        "source": "2026-08-12/20260812_V04_object-lifecycle-bottle-removal_take01.mp4",
        "output": "edgesentinel-demo-04-object-lifecycle-zh-cn-720p.mp4",
        "cover": "demo-04-object-lifecycle.jpg",
        "cover_second": 70,
        "start_seconds": 8,
        "redactions": (),
    },
    {
        "id": "V05",
        "source": "2026-08-13/20260813_V05_left-behind-bottle_take01.mp4",
        "output": "edgesentinel-demo-05-left-behind-zh-cn-720p.mp4",
        "cover": "demo-05-left-behind.jpg",
        "cover_second": 75,
        "redactions": (),
    },
    {
        "id": "V06",
        "source": "2026-08-12/20260812_V06_agent-harness-skill-hooks-trace_take01.mp4",
        "output": "edgesentinel-demo-06-agent-harness-zh-cn-720p.mp4",
        "cover": "demo-06-agent-harness.jpg",
        "cover_second": 42,
        "redactions": ((120, 225, 360, 50),),
    },
    {
        "id": "V07",
        "source": "2026-08-13/20260813_V07_online-weather-offline-vision-switch_take01.mp4",
        "output": "edgesentinel-demo-07-online-offline-tools-zh-cn-720p.mp4",
        "cover": "demo-07-online-offline-tools.jpg",
        "cover_second": 40,
        "redactions": (
            (95, 315, 300, 60),
            (35, 105, 190, 28, "between(t,50,59)+between(t,78,88)"),
        ),
    },
    {
        "id": "V08",
        "source": "2026-08-13/20260813_V08_mcp-server-catalog-stdio-resources-deny_take01.mp4",
        "output": "edgesentinel-demo-08-mcp-server-zh-cn-720p.mp4",
        "cover": "demo-08-mcp-server.jpg",
        "cover_second": 18,
        "source_size": (1280, 720),
        "redactions": (
            (0, 0, 470, 42, "gte(t,28)"),
            (0, 368, 700, 48, "gte(t,28)"),
            (0, 435, 520, 32, "gte(t,28)"),
        ),
    },
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as input_file:
        while True:
            chunk = input_file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _run(command, capture=False):
    if capture:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
    else:
        process = subprocess.run(command)
    if process.returncode:
        raise RuntimeError("video command failed")
    return process.stdout if capture else ""


def _filter(profile):
    if profile.get("source_size") == (1280, 720):
        parts = ["crop=1138:640:71:70", "scale=1280:720"]
    else:
        parts = ["crop=1706:960:107:120", "scale=1280:720"]
    for redaction in profile["redactions"]:
        x, y, width, height = redaction[:4]
        box = "drawbox=x={0}:y={1}:w={2}:h={3}:color=black@0.96:t=fill".format(
            x, y, width, height
        )
        if len(redaction) == 5:
            box += ":enable='{0}'".format(redaction[4])
        parts.append(box)
    return ",".join(parts)


def _probe(ffmpeg, path):
    output = _run(
        [ffmpeg, "-hide_banner", "-i", path, "-f", "null", "NUL"],
        capture=True,
    )
    duration_match = re.search(r"Duration: ([0-9]+):([0-9]+):([0-9.]+)", output)
    video_match = re.search(r"Video: ([^\r\n]+)", output)
    audio_match = re.search(r"Audio: ([^\r\n]+)", output)
    if not duration_match or not video_match:
        raise RuntimeError("could not validate public video")
    duration = (
        int(duration_match.group(1)) * 3600
        + int(duration_match.group(2)) * 60
        + float(duration_match.group(3))
    )
    video = video_match.group(1)
    return {
        "duration_seconds": round(duration, 3),
        "codec": "h264" if "h264" in video.lower() else "unknown",
        "width": 1280 if "1280x720" in video else None,
        "height": 720 if "1280x720" in video else None,
        "audio_present": bool(audio_match),
    }


def build(ffmpeg, source_root, output_root, release):
    if not os.path.isfile(ffmpeg):
        raise ValueError("ffmpeg executable does not exist")
    os.makedirs(output_root, exist_ok=True)
    os.makedirs(COVER_DIR, exist_ok=True)
    results = []
    for profile in PROFILES:
        source = os.path.join(source_root, *profile["source"].split("/"))
        output = os.path.join(output_root, profile["output"])
        cover = os.path.join(COVER_DIR, profile["cover"])
        if not os.path.isfile(source):
            raise ValueError("source video is missing: {0}".format(profile["id"]))
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        if profile.get("start_seconds"):
            command.extend(["-ss", str(profile["start_seconds"])])
        command.extend([
            "-i", source,
            "-map_metadata", "-1", "-map_chapters", "-1", "-an",
            "-vf", _filter(profile),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            output,
        ])
        _run(command)
        _run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(profile["cover_second"]), "-i", output,
            "-frames:v", "1", "-q:v", "3", cover,
        ])
        properties = _probe(ffmpeg, output)
        if (
            properties["codec"] != "h264"
            or properties["width"] != 1280
            or properties["height"] != 720
            or properties["audio_present"]
        ):
            raise RuntimeError("public video validation failed: {0}".format(profile["id"]))
        results.append({
            "id": profile["id"],
            "file": profile["output"],
            "bytes": os.path.getsize(output),
            "sha256": _sha256(output),
            "duration_seconds": properties["duration_seconds"],
            "video_codec": properties["codec"],
            "resolution": "1280x720",
            "audio_present": False,
            "metadata_removed": True,
            "cover": "docs/media/covers/{0}".format(profile["cover"]),
        })
        print("Built {0}: {1}".format(profile["id"], profile["output"]))
    manifest = {
        "schema_version": "1.0",
        "status": "VERIFIED",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "release": release,
        "video_count": len(results),
        "audio_removed": True,
        "metadata_removed": True,
        "source_recordings_in_git": False,
        "videos": results,
    }
    manifest_path = os.path.join(output_root, "video-release-manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as output_file:
        json.dump(manifest, output_file, ensure_ascii=False, indent=2, sort_keys=True)
        output_file.write("\n")
    return manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build public EdgeSentinel videos.")
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--release",
        default="v" + open(
            os.path.join(PROJECT_DIR, "VERSION"), "r", encoding="utf-8"
        ).read().strip(),
    )
    args = parser.parse_args(argv)
    manifest_path = build(
        os.path.abspath(args.ffmpeg),
        os.path.abspath(args.source_root),
        os.path.abspath(args.output_root),
        args.release,
    )
    print("Video release manifest: {0}".format(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
