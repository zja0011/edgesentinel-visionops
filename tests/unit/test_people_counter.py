import unittest

from packages.analytics.people_counter import PeopleCounter


def track(
    track_id=1,
    class_name="person",
    hits=3,
    missed_frames=0,
):
    return {
        "track_id": track_id,
        "class_name": class_name,
        "hits": hits,
        "missed_frames": missed_frames,
    }


class PeopleCounterTests(unittest.TestCase):
    def test_ignores_unconfirmed_and_non_person_tracks(self):
        counter = PeopleCounter(min_confirmed_hits=3)
        result = counter.update(
            [track(hits=2), track(2, class_name="chair", hits=20)],
            frame_id=1,
        )

        self.assertEqual(result["current_people"], 0)
        self.assertEqual(result["confirmed_tracks_total"], 0)

    def test_counts_confirmed_person_once(self):
        counter = PeopleCounter(min_confirmed_hits=3)
        first = counter.update([track(hits=3)], frame_id=3)
        second = counter.update([track(hits=4)], frame_id=4)

        self.assertEqual(first["current_people"], 1)
        self.assertEqual(second["current_people"], 1)
        self.assertEqual(second["confirmed_tracks_total"], 1)

    def test_short_miss_stays_in_occupancy_but_not_visible(self):
        counter = PeopleCounter(
            min_confirmed_hits=1, occupancy_grace_frames=2
        )
        counter.update([track()], frame_id=1)
        result = counter.update([track(missed_frames=2)], frame_id=3)

        self.assertEqual(result["current_people"], 1)
        self.assertEqual(result["visible_people"], 0)

    def test_person_is_lost_after_grace_period(self):
        counter = PeopleCounter(
            min_confirmed_hits=1, occupancy_grace_frames=2
        )
        counter.update([track()], frame_id=1)
        result = counter.update([track(missed_frames=3)], frame_id=4)

        self.assertEqual(result["current_people"], 0)
        self.assertEqual(result["confirmed_tracks_total"], 1)

    def test_counts_two_people_with_distinct_track_ids(self):
        counter = PeopleCounter(min_confirmed_hits=1)
        result = counter.update([track(4), track(9)], frame_id=1)

        self.assertEqual(result["current_people"], 2)
        self.assertEqual(result["active_track_ids"], [4, 9])
        self.assertEqual(result["confirmed_tracks_total"], 2)


if __name__ == "__main__":
    unittest.main()
