---
name: investigate-removed-item
description: Investigate bounded object-removal events with exact event details and evidence integrity checks. Use when a user asks what was removed, whether an item was taken, who took an item, or requests investigation of an OBJECT_REMOVED event.
---

# Investigate a removed item

Use this workflow when the user asks whether an object was removed, asks to
investigate a removal, or asks who took an object.

1. Call `event.query` with `event_type=OBJECT_REMOVED`, a bounded `limit`, and
   the exact detector `object_class` when the user states one.
2. If an event is returned and more detail or evidence integrity is necessary,
   call `event.get_detail` and `evidence.verify_event` for the same most
   relevant exact `event_id` together in one model response. Do not spread
   these independent reads across separate model rounds.
3. Report whether evidence is valid, but never claim that integrity
   verification identifies a person.
4. Keep every conclusion tied to Tool results. A removal event proves a count
   change, not who caused it. If no identity evidence exists, explicitly say
   that the responsible person cannot be determined.
5. Do not call tools outside `required_tools`. Do not acknowledge events,
   capture snapshots, restart the camera, generate files, or perform cleanup.

Answer in the user's language. Include event time, camera, zone, object class,
count change, disposition, and evidence status only when those fields are
available. State when data is stale, absent, incomplete, or outside the query
window.
