"""Build a checksum manifest for unmodified EdgeSentinel demo recordings."""

from __future__ import print_function

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess


PROFILES = (
    ("V01", "2026-08-12/20260812_V01_end-to-end-dashboard-agent-mcp_take01.mp4", "edgesentinel-original-01-end-to-end-dashboard-agent-mcp.mp4"),
    ("V02", "2026-08-12/20260812_V02_live-vision-people-objects-tracks_take01.mp4", "edgesentinel-original-02-live-vision-people-objects-tracks.mp4"),
    ("V03", "2026-08-13/20260813_V03_zone-enter-dwell-exit-track_take01.mp4", "edgesentinel-original-03-zone-enter-dwell-exit-track.mp4"),
    ("V04", "2026-08-12/20260812_V04_object-lifecycle-bottle-removal_take01.mp4", "edgesentinel-original-04-object-lifecycle-bottle-removal.mp4"),
    ("V05", "2026-08-13/20260813_V05_left-behind-bottle_take01.mp4", "edgesentinel-original-05-left-behind-bottle.mp4"),
    ("V06", "2026-08-12/20260812_V06_agent-harness-skill-hooks-trace_take01.mp4", "edgesentinel-original-06-agent-harness-skill-hooks-trace.mp4"),
    ("V07", "2026-08-13/20260813_V07_online-weather-offline-vision-switch_take01.mp4", "edgesentinel-original-07-online-weather-offline-vision-switch.mp4"),
    ("V08", "2026-08-13/20260813_V08_mcp-server-catalog-stdio-resources-deny_take01.mp4", "edgesentinel-original-08-mcp-server-catalog-stdio-resources-deny.mp4"),
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


def _probe(ffmpeg, path):
    process = subprocess.Popen(
        [ffmpeg, "-hide_banner", "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _, error = process.communicate()
    text = error.decode("utf-8", "replace")
    duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    video = re.search(r"Video:\s*([^,]+).*?(\d{2,5})x(\d{2,5})", text)
    audio = re.search(r"Audio:\s*([^,]+)", text)
    if not duration or not video:
        raise ValueError("video metadata is unavailable: {0}".format(path))
    seconds = (
        int(duration.group(1)) * 3600
        + int(duration.group(2)) * 60
        + float(duration.group(3))
    )
    return {
        "duration_seconds": round(seconds, 3),
        "video_codec": video.group(1).strip(),
        "width": int(video.group(2)),
        "height": int(video.group(3)),
        "audio_codec": audio.group(1).strip() if audio else None,
    }


def build(ffmpeg, source_root, release):
    videos = []
    for video_id, relative_path, asset_name in PROFILES:
        source = os.path.join(source_root, *relative_path.split("/"))
        if not os.path.isfile(source):
            raise ValueError("source video is missing: {0}".format(video_id))
        entry = {
            "id": video_id,
            "source_file": os.path.basename(source),
            "release_asset": asset_name,
            "bytes": os.path.getsize(source),
            "sha256": _sha256(source),
            "modified": False,
        }
        entry.update(_probe(ffmpeg, source))
        videos.append(entry)
    return {
        "schema_version": "1.0",
        "status": "VERIFIED",
        "release": release,
        "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "video_count": len(videos),
        "total_bytes": sum(item["bytes"] for item in videos),
        "source_recordings_in_git": False,
        "videos_modified": False,
        "videos": videos,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--release", default="v0.1.0-dev.1")
    args = parser.parse_args()
    result = build(
        os.path.abspath(args.ffmpeg),
        os.path.abspath(args.source_root),
        args.release,
    )
    with open(os.path.abspath(args.output), "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2, sort_keys=True)
        output_file.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
