"""Kit v122: the inbound alert knows the drain's schedule. With settings.inbound_schedule an item is late only when it
came in before a run that was expected and is now past its grace time (an overnight or weekend wait is not late); the
drain records its time (tasks.json inbound.last_run, once a quiet day) so a drain that stopped shows. Without a schedule the
older rule (settings.inbound_alert_minutes) stays."""
import datetime as dt
import json
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_kit_v112 import Board, KIT, item, keeptrack, read  # noqa: E402

UTC = dt.timezone.utc
DAYS = ["mon", "tue", "wed", "thu", "fri"]
TIMES = ["09:07", "11:07", "14:07", "16:07"]


def at(text):
    return dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


def schedule(**over):
    raw = {"days": DAYS, "times": TIMES, "tz": "Europe/London", "grace_minutes": 30}
    raw.update(over)
    return {"settings": {"inbound_schedule": raw}}


def attention(data, now_at, names):
    with mock.patch.object(keeptrack, "inbound_files", return_value=[(f"inbound/{n}", n) for n in names]):
        return keeptrack.inbound_attention(data, at(now_at))


class Release(unittest.TestCase):
    def test_release_122_is_consistent(self):
        version = json.loads(read("board/kit/manifest.json"))["version"]
        self.assertEqual(version, 122)
        self.assertEqual(str(version), re.search(r"^KIT_VERSION = (\d+)", read("board/kit/keeptrack.py"), re.M)[1])
        self.assertIn(f"const PAGE_KIT = {version};", read("board/board.js"))
        for plugin in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            self.assertEqual(f"0.{version}.0", json.loads(read(f"board/kit/{plugin}/plugin.json"))["version"])
        self.assertIn("### v122 (schema 4)", read("board/kit/UPGRADING.md"))
        self.assertIn("Kit v122:", read("CHANGELOG.md"))

    def test_docs_know_the_schedule(self):
        for path in ("board/kit/INBOUND.md", "board/kit/README.md"):
            self.assertIn("inbound-schedule", read(path))
            self.assertIn("last_run", read(path))


class ExpectedRun(unittest.TestCase):
    def sched(self, **over):
        return keeptrack.inbound_schedule(schedule(**over))

    def test_the_latest_run_past_its_grace_time(self):
        s = self.sched()
        self.assertEqual(at("2026-10-30T14:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-30T16:30:00")))   # Fri, GMT
        self.assertEqual(at("2026-10-30T16:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-30T16:37:00")))   # grace is inclusive

    def test_a_weekend_looks_back_to_friday(self):
        s = self.sched()
        self.assertEqual(at("2026-10-30T16:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-31T03:00:00")))   # Sat
        self.assertEqual(at("2026-10-30T16:07:00"), keeptrack.inbound_expected_run(s, at("2026-11-02T09:20:00")))   # Mon, grace not over
        self.assertEqual(at("2026-11-02T09:07:00"), keeptrack.inbound_expected_run(s, at("2026-11-02T09:40:00")))

    def test_the_time_zone_and_summer_time(self):
        s = self.sched()   # Fri 23 Oct is summer time: 16:07 in London is 15:07 UTC
        self.assertEqual(at("2026-10-23T15:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-23T16:00:00")))
        s = self.sched(tz="America/New_York")
        self.assertEqual(at("2026-10-30T20:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-30T21:00:00")))   # EDT, UTC-4

    def test_first_run_of_the_day(self):
        s = self.sched()
        self.assertEqual(at("2026-10-30T09:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-30T16:30:00"), first_only=True))
        self.assertEqual(at("2026-10-30T09:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-31T10:00:00"), first_only=True))   # Sat: Friday's
        self.assertEqual(at("2026-10-29T09:07:00"), keeptrack.inbound_expected_run(s, at("2026-10-30T09:20:00"), first_only=True))   # grace not over

    def test_no_zone_means_utc_for_every_reader(self):
        data = {"settings": {"inbound_schedule": {"days": DAYS, "times": ["09:00"]}, "kit_owner": "osouthgate"},
                "people": [{"github": "osouthgate", "timezone": "Europe/London"}, {"github": "JezHub", "timezone": "America/New_York"}]}
        got = set()
        for user in ("osouthgate", "JezHub", "nobody"):
            with mock.patch.dict(os.environ, {"BOARD_USER": user}):
                got.add(keeptrack.inbound_expected_run(keeptrack.inbound_schedule(data), at("2026-11-11T15:00:00")))
        self.assertEqual({at("2026-11-11T09:00:00")}, got)

    def test_a_bad_schedule_is_no_schedule(self):
        for raw in ({"days": ["funday"], "times": ["09:00"]}, {"days": DAYS, "times": ["25:00"]}, {"days": DAYS, "times": []},
                    {"days": DAYS, "times": ["09:00"], "tz": "Not/AZone"}, {"days": DAYS, "times": ["09:00"], "grace_minutes": 0},
                    {"days": DAYS, "times": ["09:00"], "grace_minutes": True}, "mon 09:00"):
            self.assertIsNone(keeptrack.inbound_schedule({"settings": {"inbound_schedule": raw}}), raw)


class Alert(unittest.TestCase):
    NAME = "20261030T170000Z-rainshift-contact-a.json"   # Fri 17:00, after the last run of the day

    def test_an_overnight_and_weekend_wait_is_not_late(self):
        for now_at in ("2026-10-30T20:00:00", "2026-10-31T03:00:00", "2026-11-01T12:00:00", "2026-11-02T09:20:00"):
            self.assertEqual([], attention(schedule(), now_at, [self.NAME]), now_at)

    def test_an_item_that_missed_a_run_is_late(self):
        out = attention(schedule(), "2026-11-02T09:40:00", [self.NAME])
        self.assertEqual(1, len(out))
        self.assertIn("missed the Mon 09:07 run", out[0])
        late = "20261030T140000Z-rainshift-contact-b.json"   # came in before Friday's 14:07 run
        out = attention(schedule(), "2026-10-30T14:40:00", [late])
        self.assertIn("missed the Fri 14:07 run", out[0])

    def test_an_item_within_the_grace_time_is_not_late(self):
        self.assertEqual([], attention(schedule(), "2026-10-30T14:20:00", ["20261030T140000Z-rainshift-contact-b.json"]))

    def test_a_name_without_a_time_is_always_late(self):
        out = attention(schedule(), "2026-10-30T14:20:00", ["odd.json"])
        self.assertIn("no time in the name", out[0])

    def test_a_failed_item_always_shows(self):
        data = dict(schedule(), inbound={"failed": {self.NAME: {"error": "bad", "since": "2026-10-30T17:01:00.000Z"}}})
        self.assertIn("inbound failed", attention(data, "2026-10-30T17:05:00", [self.NAME])[0])

    def test_without_a_schedule_the_old_rule_stays(self):
        self.assertEqual([], attention({}, "2026-10-30T18:00:00", [self.NAME]))   # 1 hour
        self.assertIn("inbound waiting", attention({}, "2026-10-30T19:30:00", [self.NAME])[0])   # 2.5 hours
        data = {"settings": {"inbound_schedule": {"days": ["funday"], "times": ["09:00"]}, "inbound_alert_minutes": 30}}
        out = attention(data, "2026-10-30T17:40:00", [self.NAME])   # a bad one falls back, and says why
        self.assertTrue(any(x.startswith("inbound waiting") for x in out))
        self.assertTrue(any("schedule is set but not used" in x and "days must be" in x for x in out), out)

    def test_a_last_run_in_the_future_does_not_hide_a_dead_drain(self):
        data = dict(schedule(), inbound={"last_run": {"at": "2026-11-12T09:08:00.000Z", "handled": 0, "failed": 0}})
        self.assertIn("in the future", attention(data, "2026-11-11T09:40:00", [])[0])
        data["inbound"]["last_run"]["at"] = "2026-11-11T09:12:00.000Z"   # a few minutes ahead of the checker is a normal clock difference
        self.assertEqual([], attention(data, "2026-11-11T09:10:00", []))

    def test_a_drain_that_has_not_run(self):
        def data(last):
            d = schedule()
            if last:
                d["inbound"] = {"last_run": {"at": last, "handled": 0, "failed": 0}}
            return d
        self.assertIn("inbound drain has not run since 2026-10-30 09:08 UTC",
                      attention(data("2026-10-30T09:08:01.000Z"), "2026-11-02T09:40:00", [])[0])
        self.assertEqual([], attention(data("2026-11-02T09:08:01.000Z"), "2026-11-02T09:40:00", []))
        self.assertEqual([], attention(data("2026-10-30T09:08:01.000Z"), "2026-11-02T09:20:00", []))   # Monday's grace time is not over
        self.assertEqual([], attention(data("2026-10-30T09:08:01.000Z"), "2026-11-01T12:00:00", []))   # the weekend
        self.assertEqual([], attention(data(None), "2026-11-02T09:40:00", []))   # a board that never recorded a run is not alarmed
        self.assertEqual([], attention({"inbound": {"last_run": {"at": "2020-01-01T00:00:00Z"}}}, "2026-11-02T09:40:00", []))   # no schedule


class Cli(Board):
    def set_last_run(self, stamp):
        root = self.root()
        root["inbound"] = {"last_run": {"at": stamp, "handled": 0, "failed": 0}}
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(root, f)

    def set_schedule(self):
        self.kt("inbound-schedule", "--days", "daily", "--time", "00:01", "--tz", "UTC", "--grace", "1")

    def test_an_empty_run_without_a_schedule_records_nothing(self):
        before = self.root()
        self.kt("inbound")
        self.assertEqual(before, self.root())

    def test_a_run_with_items_records_its_time_even_without_a_schedule(self):
        self.put(item("a"))
        self.kt("inbound")
        self.assertEqual(1, self.root()["inbound"]["last_run"]["handled"])

    def test_an_empty_run_records_its_time_once_a_day(self):
        self.set_schedule()
        self.kt("inbound")
        first = self.root()["inbound"]["last_run"]
        self.assertEqual({"handled": 0, "failed": 0}, {k: first[k] for k in ("handled", "failed")})
        before = open(os.path.join(self.board, "tasks.json"), encoding="utf8").read()
        out = self.kt("inbound").stdout
        self.assertIn("nothing waiting", out)
        self.assertEqual(before, open(os.path.join(self.board, "tasks.json"), encoding="utf8").read())   # no second change the same day

    def test_an_empty_run_on_a_new_day_records_again(self):
        self.set_schedule()
        self.set_last_run("2020-01-01T09:08:00.000Z")
        self.kt("inbound")
        self.assertGreater(self.root()["inbound"]["last_run"]["at"], "2026")

    def test_a_manual_run_before_the_first_expected_run_does_not_hide_a_stop(self):
        self.kt("inbound-schedule", "--days", "daily", "--time", "00:01", "--tz", "UTC", "--grace", "1")
        today = dt.datetime.now(UTC).strftime("%Y-%m-%d")
        self.set_last_run(f"{today}T00:00:30.000Z")   # before today's 00:01 run (when that has passed)
        root = self.root()
        root["settings"]["inbound_schedule"] = {"days": list(keeptrack.INBOUND_DAYS), "times": ["00:01"], "tz": "UTC", "grace_minutes": 1}
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(root, f)
        self.kt("inbound")
        if dt.datetime.now(UTC).strftime("%H:%M") >= "00:01":
            self.assertGreater(self.root()["inbound"]["last_run"]["at"], f"{today}T00:01")

    def test_a_run_that_handles_items_records_the_counts(self):
        self.put(item("a"))
        self.put(item("b"))
        self.put("not json", name="20261029T170200Z-rainshift-contact-bad.json")
        self.kt("inbound", ok=False)
        last = self.root()["inbound"]["last_run"]
        self.assertEqual((2, 1), (last["handled"], last["failed"]))

    def test_the_schedule_is_set_shown_and_cleared(self):
        self.assertIn("no schedule set", self.kt("inbound-schedule").stdout)
        self.kt("inbound-schedule", "--days", "mon-fri", "--time", "11:07", "--time", "09:07")   # no --tz: a zone is stored, never left to each reader
        self.assertEqual("UTC", self.root()["settings"]["inbound_schedule"]["tz"])
        self.kt("inbound-schedule", "--tz", "Europe/London")
        self.assertEqual({"days": DAYS, "times": ["09:07", "11:07"], "tz": "Europe/London", "grace_minutes": 30},
                         self.root()["settings"]["inbound_schedule"])
        self.assertIn("mon,tue,wed,thu,fri at 09:07, 11:07", self.kt("inbound-schedule").stdout)
        self.assertIn("schedule: mon,tue,wed,thu,fri", self.kt("inbound", "--status").stdout)
        self.kt("inbound-schedule", "--grace", "45")
        self.assertEqual(45, self.root()["settings"]["inbound_schedule"]["grace_minutes"])
        self.kt("inbound-schedule", "--clear")
        self.assertNotIn("inbound_schedule", self.root()["settings"])

    def test_a_stored_schedule_that_cannot_be_used_is_named(self):
        root = self.root()
        root["settings"] = dict(root.get("settings") or {}, inbound_schedule={"days": ["mon"], "times": ["09:00"], "tz": "Not/AZone"})
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(root, f)
        self.assertIn("schedule is set but not used (tz must be", self.kt("inbound-schedule").stdout)
        self.assertIn("schedule is set but not used", self.kt("inbound", "--status").stdout)
        self.assertIn("inbound schedule is set but not used", self.kt("list", "--attention").stdout)

    def test_a_bad_schedule_is_refused_and_nothing_is_saved(self):
        for args in (["--days", "funday", "--time", "09:00"], ["--days", "mon", "--time", "9am"], ["--days", "mon"],
                     ["--days", "mon", "--time", "09:00", "--tz", "Nowhere/Land"], ["--days", "mon", "--time", "09:00", "--grace", "0"]):
            self.assertNotEqual(0, self.kt("inbound-schedule", *args, ok=False).returncode, args)
        self.assertNotIn("inbound_schedule", self.root().get("settings", {}))

    def test_an_agent_may_only_clear_the_schedule(self):
        self.kt("inbound-schedule", "--days", "mon-fri", "--time", "09:07", "--tz", "UTC")
        agent = dict(BOARD_AGENT="claude", BOARD_SESSION="abc12345")
        p = self.kt("inbound-schedule", "--days", "daily", "--time", "03:00", ok=False, **agent)
        self.assertNotEqual(0, p.returncode)
        self.assertIn("only clear", p.stderr + p.stdout)
        self.assertEqual(DAYS, self.root()["settings"]["inbound_schedule"]["days"])
        self.kt("inbound-schedule", "--clear", **agent)
        self.assertNotIn("inbound_schedule", self.root()["settings"])

    def test_attention_names_a_stopped_drain(self):
        self.kt("inbound-schedule", "--days", "daily", "--time", "00:01", "--tz", "UTC", "--grace", "1")
        self.set_last_run("2020-01-01T09:08:00.000Z")
        root = self.root()
        root["settings"] = dict(root.get("settings") or {}, inbound_schedule={"days": list(keeptrack.INBOUND_DAYS), "times": ["00:01"],
                                                                              "tz": "UTC", "grace_minutes": 1})
        with open(os.path.join(self.board, "tasks.json"), "w", encoding="utf8") as f:
            json.dump(root, f)
        self.assertIn("inbound drain has not run since 2020-01-01 09:08 UTC", self.kt("list", "--attention").stdout)
        self.assertIn("inbound drain has not run since 2020-01-01 09:08 UTC", self.kt("inbound", "--status").stdout)


if __name__ == "__main__":
    unittest.main()
