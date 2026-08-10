"""Run Jetson object detection and emit versioned JSON Lines results."""

import argparse
import json
import os
import sys
import time

from packages.vision.jetson_detector import JetsonDetector
from packages.vision.schemas import FrameResult, beijing_timestamp
from packages.vision.state_store import CurrentVisionStateStore
from packages.vision.frame_store import LatestFrameStore
from packages.vision.model_manifest import (
    VisionModelManifestStore,
    build_vision_model_manifest,
)
from packages.tracking.iou_tracker import IoUTracker
from packages.analytics.people_counter import PeopleCounter
from packages.analytics.performance import VisionPerformanceTracker
from packages.analytics.zone_reloader import ZoneConfigReloader
from packages.analytics.inventory import InventoryEngine
from packages.analytics.left_behind import LeftBehindEngine
from packages.analytics.track_history import build_track_history
from packages.events.engine import ZoneEventEngine
from packages.events.store import JsonlEventStore
from packages.events.sqlite_store import SqliteEventStore
from packages.evidence.manager import EvidenceManager


def build_parser():
    parser = argparse.ArgumentParser(
        description="Capture frames, run detectNet, and emit structured JSON."
    )
    parser.add_argument("--input", default="/dev/video0", help="video input URI")
    parser.add_argument(
        "--output",
        default="display://0",
        help="video output URI; pass an empty string for headless mode",
    )
    parser.add_argument("--camera-id", default="camera_01")
    parser.add_argument("--network", default="ssd-mobilenet-v2")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--model-engine",
        default="",
        help=(
            "exact TensorRT engine path used for the read-only model "
            "integrity manifest"
        ),
    )
    parser.add_argument(
        "--model-root",
        default="/jetson-inference/data/networks",
        help=(
            "trusted model root used to convert the engine path to a "
            "safe relative path"
        ),
    )
    parser.add_argument(
        "--model-manifest-output",
        default="data/state/current-model.json",
        help=(
            "atomic vision model provenance file; empty disables it"
        ),
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--json-every",
        type=int,
        default=1,
        help="emit JSON every N captured frames",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="optional JSONL file; stdout is always enabled",
    )
    parser.add_argument(
        "--state-output",
        default="data/state/current-vision.json",
        help="atomic latest-state JSON file; empty disables it",
    )
    parser.add_argument(
        "--state-every",
        type=int,
        default=5,
        help="overwrite the latest state every N captured frames",
    )
    parser.add_argument(
        "--live-frame-output",
        default="",
        help="atomic latest annotated JPEG; empty disables it",
    )
    parser.add_argument(
        "--live-frame-every",
        type=int,
        default=10,
        help="overwrite the latest JPEG every N captured frames",
    )
    parser.add_argument(
        "--live-frame-quality",
        type=int,
        default=80,
        help="latest dashboard JPEG quality from 1 to 100",
    )
    parser.add_argument(
        "--tracker-iou",
        type=float,
        default=0.3,
        help="minimum IoU required to preserve a track ID",
    )
    parser.add_argument(
        "--tracker-max-missed",
        type=int,
        default=10,
        help="frames to retain a temporarily missing track",
    )
    parser.add_argument(
        "--people-min-hits",
        type=int,
        default=3,
        help="detections required before a person track affects occupancy",
    )
    parser.add_argument(
        "--people-grace-frames",
        type=int,
        default=10,
        help="temporary missed frames retained in current occupancy",
    )
    parser.add_argument(
        "--zones",
        default="configs/zones.json",
        help="normalized polygon zone configuration; empty disables zones",
    )
    parser.add_argument(
        "--zone-reload-every",
        type=int,
        default=30,
        help="frames between fail-safe zone configuration checks",
    )
    parser.add_argument(
        "--event-output",
        default="data/events/zone-events.jsonl",
        help="append-only JSONL event file; empty disables persistence",
    )
    parser.add_argument(
        "--event-db",
        default="data/events/edgesentinel.db",
        help="SQLite event database; empty disables database persistence",
    )
    parser.add_argument(
        "--zone-enter-confirm",
        type=int,
        default=15,
        help="consecutive in-zone frames required for ZONE_ENTER",
    )
    parser.add_argument(
        "--zone-exit-confirm",
        type=int,
        default=30,
        help="consecutive out-of-zone frames required for ZONE_EXIT",
    )
    parser.add_argument(
        "--zone-dwell-seconds",
        type=float,
        default=20.0,
        help=(
            "seconds inside one zone before one ZONE_DWELL event; "
            "zero disables dwell events"
        ),
    )
    parser.add_argument(
        "--evidence-dir",
        default="data/evidence",
        help="event image directory; empty disables evidence capture",
    )
    parser.add_argument(
        "--evidence-quality",
        type=int,
        default=90,
        help="JPEG evidence quality from 1 to 100",
    )
    parser.add_argument(
        "--evidence-checkpoint-every",
        type=int,
        default=15,
        help="frames between rolling stable-inventory snapshots",
    )
    parser.add_argument(
        "--inventory-classes",
        default=(
            "backpack,handbag,suitcase,bottle,cup,laptop,"
            "cell phone,book,mouse"
        ),
        help="comma-separated object classes; empty disables inventory",
    )
    parser.add_argument(
        "--inventory-min-hits",
        type=int,
        default=3,
        help="track hits required before an object can affect inventory",
    )
    parser.add_argument(
        "--inventory-appear-confirm",
        type=int,
        default=15,
        help="consecutive frames required to confirm a count increase",
    )
    parser.add_argument(
        "--inventory-remove-confirm",
        type=int,
        default=30,
        help="consecutive frames required to confirm a count decrease",
    )
    parser.add_argument(
        "--left-behind-classes",
        default="backpack,handbag,suitcase,bottle",
        help="comma-separated classes monitored for left-behind events",
    )
    parser.add_argument(
        "--left-behind-confirm",
        type=int,
        default=200,
        help="no-person frames required for OBJECT_LEFT_BEHIND",
    )
    parser.add_argument(
        "--left-behind-rearm-people",
        type=int,
        default=15,
        help="person-present frames required to rearm an alert",
    )
    return parser


def validate_args(args, parser):
    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")
    if args.width <= 0 or args.height <= 0:
        parser.error("--width and --height must be positive")
    if args.json_every <= 0:
        parser.error("--json-every must be positive")
    if args.state_every <= 0:
        parser.error("--state-every must be positive")
    if args.live_frame_every <= 0:
        parser.error("--live-frame-every must be positive")
    if not 1 <= args.live_frame_quality <= 100:
        parser.error("--live-frame-quality must be between 1 and 100")
    if not 0.0 <= args.tracker_iou <= 1.0:
        parser.error("--tracker-iou must be between 0 and 1")
    if args.tracker_max_missed < 0:
        parser.error("--tracker-max-missed must be non-negative")
    if args.people_min_hits <= 0:
        parser.error("--people-min-hits must be positive")
    if args.people_grace_frames < 0:
        parser.error("--people-grace-frames must be non-negative")
    if args.zone_reload_every <= 0:
        parser.error("--zone-reload-every must be positive")
    if args.zone_enter_confirm <= 0:
        parser.error("--zone-enter-confirm must be positive")
    if args.zone_exit_confirm <= 0:
        parser.error("--zone-exit-confirm must be positive")
    if args.zone_dwell_seconds < 0:
        parser.error("--zone-dwell-seconds must be non-negative")
    if not 1 <= args.evidence_quality <= 100:
        parser.error("--evidence-quality must be between 1 and 100")
    if args.evidence_checkpoint_every <= 0:
        parser.error("--evidence-checkpoint-every must be positive")
    if args.inventory_min_hits <= 0:
        parser.error("--inventory-min-hits must be positive")
    if args.inventory_appear_confirm <= 0:
        parser.error("--inventory-appear-confirm must be positive")
    if args.inventory_remove_confirm <= 0:
        parser.error("--inventory-remove-confirm must be positive")
    if args.left_behind_confirm <= 0:
        parser.error("--left-behind-confirm must be positive")
    if args.left_behind_rearm_people <= 0:
        parser.error("--left-behind-rearm-people must be positive")


def emit_json(result, output_file):
    line = json.dumps(
        result.to_dict(), ensure_ascii=False, separators=(",", ":")
    )
    print(line, flush=True)
    if output_file is not None:
        output_file.write(line + "\n")
        output_file.flush()


def open_json_output(path):
    if not path:
        return None
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        os.makedirs(parent)
    return open(path, "a", encoding="utf-8")


def run(args):
    detector = JetsonDetector(args.network, args.threshold)
    if args.model_manifest_output:
        try:
            manifest = build_vision_model_manifest(
                args.network,
                args.threshold,
                args.model_engine,
                args.model_root,
            )
            VisionModelManifestStore(
                args.model_manifest_output
            ).write(manifest)
        except Exception as error:
            print(
                json.dumps(
                    {
                        "event": "MODEL_MANIFEST_ERROR",
                        "error": str(error),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                file=sys.stderr,
                flush=True,
            )
    tracker = IoUTracker(args.tracker_iou, args.tracker_max_missed)
    people_counter = PeopleCounter(
        min_confirmed_hits=args.people_min_hits,
        occupancy_grace_frames=args.people_grace_frames,
    )
    zone_reloader = (
        ZoneConfigReloader(
            args.zones,
            check_interval_frames=args.zone_reload_every,
        )
        if args.zones
        else None
    )
    zone_engine = (
        zone_reloader.engine
        if zone_reloader is not None
        else None
    )
    zone_renderer = (
        detector.create_zone_renderer(zone_engine.zones)
        if zone_engine is not None
        and (
            args.output
            or args.evidence_dir
            or args.live_frame_output
        )
        else None
    )
    zone_event_engine = (
        ZoneEventEngine(
            args.zone_enter_confirm,
            args.zone_exit_confirm,
            dwell_seconds=args.zone_dwell_seconds,
        )
        if zone_engine is not None
        else None
    )
    inventory_classes = [
        value.strip()
        for value in args.inventory_classes.split(",")
        if value.strip()
    ]
    inventory_engine = (
        InventoryEngine(
            inventory_classes,
            minimum_hits=args.inventory_min_hits,
            appear_confirm_frames=args.inventory_appear_confirm,
            remove_confirm_frames=args.inventory_remove_confirm,
        )
        if inventory_classes
        else None
    )
    left_behind_classes = [
        value.strip()
        for value in args.left_behind_classes.split(",")
        if value.strip()
    ]
    left_behind_engine = (
        LeftBehindEngine(
            left_behind_classes,
            confirm_frames=args.left_behind_confirm,
            rearm_people_frames=args.left_behind_rearm_people,
        )
        if inventory_engine is not None and left_behind_classes
        else None
    )
    performance_tracker = VisionPerformanceTracker(
        window_size=120,
        minimum_fps=5.0,
        maximum_p95_ms=200.0,
    )
    source = detector.create_source(args.input, args.width, args.height)
    output = detector.create_output(args.output) if args.output else None
    output_file = open_json_output(args.json_output)
    state_store = (
        CurrentVisionStateStore(args.state_output)
        if args.state_output
        else None
    )
    live_frame_store = (
        LatestFrameStore(
            args.live_frame_output,
            detector.save_image,
            quality=args.live_frame_quality,
        )
        if args.live_frame_output
        else None
    )
    jsonl_event_store = (
        JsonlEventStore(args.event_output) if args.event_output else None
    )
    sqlite_event_store = (
        SqliteEventStore(args.event_db) if args.event_db else None
    )
    evidence_manager = (
        EvidenceManager(
            args.evidence_dir,
            detector.save_image,
            quality=args.evidence_quality,
            checkpoint_interval_frames=args.evidence_checkpoint_every,
            path_root=os.getcwd(),
        )
        if (
            zone_event_engine is not None or inventory_engine is not None
        )
        and args.evidence_dir
        else None
    )

    frame_id = 0
    try:
        # A newly-created videoSource may report IsStreaming() == False until
        # its first Capture() call opens the pipeline.  Capture first, then use
        # IsStreaming() to distinguish a timeout from end-of-stream.
        while True:
            image = source.Capture()
            if image is None:
                if not source.IsStreaming():
                    break
                continue

            frame_id += 1
            zone_reload_result = (
                zone_reloader.poll(frame_id)
                if zone_reloader is not None
                else None
            )
            if zone_reload_result is not None:
                print(
                    json.dumps(
                        {
                            "event": "ZONE_CONFIG_RELOAD",
                            "result": zone_reload_result,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    file=sys.stderr,
                    flush=True,
                )
                if zone_reload_result["status"] == "reloaded":
                    zone_engine = zone_reloader.engine
                    if zone_renderer is not None:
                        zone_renderer.update_zones(
                            zone_engine.zones
                        )
            started = time.perf_counter()
            detections = detector.detect(image)
            detections = tracker.update(detections, frame_id)
            active_tracks = tracker.active_tracks(include_missed=True)
            people = people_counter.update(active_tracks, frame_id)
            if zone_engine is not None:
                detections = zone_engine.annotate_detections(
                    detections, image.width, image.height
                )
                zones = zone_engine.snapshot(
                    active_tracks, image.width, image.height
                )
            else:
                zones = []
            frame_timestamp = beijing_timestamp()
            if zone_event_engine is not None:
                events = zone_event_engine.update(
                    zones,
                    active_tracks,
                    frame_id,
                    frame_timestamp,
                    args.camera_id,
                    monotonic_time=time.monotonic(),
                )
            else:
                events = []
            if inventory_engine is not None:
                inventory, inventory_events = inventory_engine.update(
                    active_tracks,
                    frame_id,
                    frame_timestamp,
                    args.camera_id,
                )
                events.extend(inventory_events)
            else:
                inventory = {}
            if left_behind_engine is not None:
                left_behind, left_behind_events = (
                    left_behind_engine.update(
                        inventory,
                        people,
                        frame_id,
                        frame_timestamp,
                        args.camera_id,
                    )
                )
                events.extend(left_behind_events)
            else:
                left_behind = {}
            inference_ms = (time.perf_counter() - started) * 1000.0
            performance = performance_tracker.update(
                inference_ms,
                monotonic_time=time.monotonic(),
            )

            if zone_renderer is not None:
                zone_renderer.render(image, zones)

            if evidence_manager is not None and inventory:
                try:
                    evidence_manager.update_inventory_snapshot(
                        inventory,
                        image,
                        frame_id,
                    )
                except Exception as error:
                    for event in events:
                        event.details["checkpoint_error"] = str(error)

            for event in events:
                if evidence_manager is not None:
                    try:
                        evidence_manager.save(event, image)
                    except Exception as error:
                        event.details["evidence_error"] = str(error)
                if jsonl_event_store is not None:
                    jsonl_event_store.append(event)
                if sqlite_event_store is not None:
                    sqlite_event_store.append(event)

            if output is not None:
                output.Render(image)
                output.SetStatus(
                    "EdgeSentinel | {0:.1f} FPS | {1} objects".format(
                        performance["processing_fps"],
                        len(detections),
                    )
                )

            if (
                live_frame_store is not None
                and frame_id % args.live_frame_every == 0
            ):
                live_frame_store.write(image)

            emit_frame = frame_id % args.json_every == 0
            persist_state = (
                state_store is not None
                and frame_id % args.state_every == 0
            )
            if emit_frame or persist_state:
                track_history = build_track_history(
                    tracker.active_tracks(
                        include_missed=True,
                        include_trajectory=True,
                    ),
                    detections,
                    image.width,
                    image.height,
                )
                result = FrameResult(
                    frame_id=frame_id,
                    timestamp=frame_timestamp,
                    camera_id=args.camera_id,
                    source=args.input,
                    width=image.width,
                    height=image.height,
                    inference_ms=inference_ms,
                    detections=detections,
                    analytics={
                        "people": people,
                        "zones": zones,
                        "zone_config": (
                            zone_reloader.snapshot()
                            if zone_reloader is not None
                            else {
                                "enabled": False,
                                "status": "disabled",
                            }
                        ),
                        "inventory": inventory,
                        "left_behind": left_behind,
                        "track_history": track_history,
                        "performance": performance,
                    },
                )
            if persist_state:
                state_store.write(result)
            if emit_frame:
                emit_json(result, output_file)

            if output is not None and not output.IsStreaming():
                break
            if not source.IsStreaming():
                break
    except KeyboardInterrupt:
        return 0
    finally:
        if output_file is not None:
            output_file.close()
        if jsonl_event_store is not None:
            jsonl_event_store.close()
        if sqlite_event_store is not None:
            sqlite_event_store.close()
        if output is not None:
            output.Close()
        source.Close()

    return 0


def main():
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)

    try:
        return run(args)
    except Exception as error:
        print(
            json.dumps(
                {
                    "error": "VISION_PROBE_FAILED",
                    "message": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
