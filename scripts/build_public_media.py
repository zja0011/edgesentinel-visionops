"""Build deterministic, redacted README media from private capture sources."""

from __future__ import print_function

import argparse
import os
from pathlib import Path

from PIL import Image, ImageFilter


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_DIR / "docs" / "media"
RESAMPLING = getattr(Image, "Resampling", Image)


def _open(source_root, relative_path):
    path = source_root / relative_path
    if not path.is_file():
        raise RuntimeError("capture source is missing: {0}".format(relative_path))
    return Image.open(str(path)).convert("RGB")


def _open_path(path):
    if not path.is_file():
        raise RuntimeError("capture source is missing: {0}".format(path))
    return Image.open(str(path)).convert("RGB")


def _pixelate(image, box, block=18):
    left, top, right, bottom = box
    left = max(0, min(image.width, left))
    right = max(left, min(image.width, right))
    top = max(0, min(image.height, top))
    bottom = max(top, min(image.height, bottom))
    region = image.crop((left, top, right, bottom))
    small_width = max(1, region.width // block)
    small_height = max(1, region.height // block)
    region = region.resize((small_width, small_height), RESAMPLING.BILINEAR)
    region = region.resize((right - left, bottom - top), RESAMPLING.NEAREST)
    region = region.filter(ImageFilter.GaussianBlur(radius=2))
    image.paste(region, (left, top))


def _fit(image, maximum_width=1800, maximum_height=1800):
    ratio = min(
        1.0,
        float(maximum_width) / float(image.width),
        float(maximum_height) / float(image.height),
    )
    if ratio < 1.0:
        image = image.resize(
            (
                max(1, int(round(image.width * ratio))),
                max(1, int(round(image.height * ratio))),
            ),
            RESAMPLING.LANCZOS,
        )
    return image


def _save_jpeg(image, relative_path, quality=86):
    path = OUTPUT_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    image = _fit(image)
    image.save(
        str(path),
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
    )
    return path


def _save_png(image, relative_path, maximum_width=1800, maximum_height=1800):
    path = OUTPUT_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    image = _fit(image, maximum_width, maximum_height)
    image.save(str(path), format="PNG", optimize=True)
    return path


def _build_hardware(source_root):
    image = _open(
        source_root,
        "01_raw_photos/2026-08-12/微信图片_20260812162736_469_8.jpg",
    )
    # Redact the external monitor's browser chrome and all readable SSH text on
    # the PC while retaining the physical PC/Jetson/Dashboard relationship.
    _pixelate(image, (1010, 105, 2560, 235), block=28)
    _pixelate(image, (2280, 665, 3890, 1900), block=28)
    _pixelate(image, (2780, 2470, 2925, 2630), block=18)
    return _save_jpeg(image, "hardware/lab-workbench.jpg", quality=84)


def _build_rig_overview(source_root):
    image = _open_path(
        source_root.parent
        / "项目所需模块总览_图片没包括PC机_PC机与开发板通过WiFissh连接.jpg"
    )
    # Remove handwritten notes and product barcodes/serial-like labels while
    # retaining the complete hardware layout.
    _pixelate(image, (0, 220, 420, 980), block=36)
    _pixelate(image, (1850, 0, 2350, 270), block=36)
    _pixelate(image, (3100, 0, image.width, 560), block=44)
    return _save_jpeg(image, "hardware/rig-overview.jpg", quality=84)


def _build_dashboard_overview(source_root):
    image = _open(
        source_root,
        "02_raw_screens/2026-08-12/界面全局截图.png",
    )
    # Keep the title, live view, zone controls, headline metrics, inventory and
    # runtime status; omit the lower event/Agent sections shown separately.
    image = image.crop((0, 0, image.width, 3450))
    _pixelate(image, (1040, 0, 1205, 145), block=18)
    return _save_png(
        image,
        "dashboard/overview.png",
        maximum_width=1205,
        maximum_height=3450,
    )


def _build_live_person(source_root):
    image = _open(
        source_root,
        "02_raw_screens/2026-08-12/"
        "20260812_D03_live-person-detection_left-zone_take01.png",
    )
    # Strongly anonymize the person's face while preserving the person box,
    # confidence, zone overlay and aggregate count.
    _pixelate(image, (35, 430, 555, 1110), block=24)
    _pixelate(image, (1030, 0, 1205, 145), block=18)
    return _save_png(image, "dashboard/live-person.png")


def _build_event_center(source_root):
    image = _open(
        source_root,
        "02_raw_screens/2026-08-12/"
        "20260812_D06_event-center_open-all-severity_take01.png",
    )
    return _save_png(image, "dashboard/event-center.png")


def _build_mcp_catalog(source_root):
    image = _open(
        source_root,
        "02_raw_screens/2026-08-12/"
        "20260812_D11_mcp-catalog-schema_take01.png",
    )
    return _save_png(image, "dashboard/mcp-catalog.png")


def _video_frame(source_root, relative_path):
    image = _open(source_root, relative_path)
    # All selected browser recordings are 1920x1080. Remove browser chrome,
    # address bar, account marker and edge margins before any other redaction.
    return image.crop((210, 110, 1690, 1080))


def _build_workbench(source_root):
    image = _video_frame(
        source_root,
        "_review_tmp/V06/frame_19_0041.5s.jpg",
    )
    # Task ID appears at x=292..735, y=442..477 in the source frame.
    _pixelate(image, (70, 315, 530, 375), block=20)
    return _save_jpeg(image, "dashboard/agent-workbench.jpg", quality=88)


def _build_model_switch(source_root):
    image = _video_frame(
        source_root,
        "98_review_temp/V07_take01/keyframes/061s.png",
    )
    # Redact the bounded short-term session identifier.
    _pixelate(image, (35, 400, 410, 455), block=18)
    return _save_png(image, "dashboard/model-switch.png")


def _build_weather_tool(source_root):
    image = _video_frame(
        source_root,
        "98_review_temp/V07_take01/keyframes/040s.png",
    )
    return _save_png(image, "dashboard/weather-tool.png")


def _build_quality_gate(source_root):
    image = _open(
        source_root,
        "02_raw_screens/2026-08-12/"
        "20260812_P01_full-tests-publication-gate_take02.png",
    )
    # Hide the SSH tab, user/host prompts, local project path and IDE workspace
    # name while preserving the commands, test count and publication verdict.
    _pixelate(image, (65, 40, 360, 85), block=18)
    _pixelate(image, (570, 0, 1380, 45), block=18)
    _pixelate(image, (65, 90, 625, 130), block=18)
    _pixelate(image, (65, 395, 625, 435), block=18)
    _pixelate(image, (65, 955, 625, 995), block=18)
    return _save_png(image, "release/quality-gates.png")


def build(source_root):
    builders = (
        _build_rig_overview,
        _build_hardware,
        _build_dashboard_overview,
        _build_live_person,
        _build_event_center,
        _build_mcp_catalog,
        _build_workbench,
        _build_model_switch,
        _build_weather_tool,
        _build_quality_gate,
    )
    outputs = []
    for builder in builders:
        outputs.append(builder(source_root))
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build redacted public media from private EdgeSentinel captures."
    )
    parser.add_argument(
        "--source-root",
        required=True,
        help="Private capture root containing 01_raw_photos and 02_raw_screens.",
    )
    args = parser.parse_args(argv)
    source_root = Path(os.path.abspath(args.source_root))
    outputs = build(source_root)
    print("Public media built: {0}".format(len(outputs)))
    for path in outputs:
        print(path.relative_to(PROJECT_DIR).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
