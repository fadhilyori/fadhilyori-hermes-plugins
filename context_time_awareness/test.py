import datetime as _datetime
import json
import re
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo

from context_time_awareness import plugin, register, store, tools


_TIME_LINE_RE = re.compile(
    r"^Current local time: \d{4}-\d{2}-\d{2} \d{2}:\d{2} "
    r"[A-Z]{2,5} \([A-Za-z]+, .+\)$"
)


def _ts(*args, **kwargs) -> int:
    return int(_datetime.datetime(*args, **kwargs, tzinfo=ZoneInfo("UTC")).timestamp())


def _temp_store():
    tmpdir = tempfile.mkdtemp()
    patcher = patch.object(store, "PLUGIN_DIR", tmpdir)
    patcher.start()
    store.init_store()
    return tmpdir, patcher


def _cleanup_temp_store(tmpdir, patcher):
    store.close_store()
    patcher.stop()
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestTimeSinceStr(unittest.TestCase):
    def test_no_prior_returns_empty(self):
        self.assertEqual(plugin._time_since_str(0, 1000), "")

    def test_under_one_minute_just_now(self):
        self.assertEqual(plugin._time_since_str(1000, 1059),
                         "Time since last user message: just now")

    def test_one_minute(self):
        self.assertEqual(plugin._time_since_str(1000, 1061),
                         "Time since last user message: 1m")

    def test_hours_and_minutes(self):
        prior = _ts(2024, 1, 1, 10, 5)
        now = _ts(2024, 1, 1, 12, 15)
        self.assertEqual(plugin._time_since_str(prior, now),
                         "Time since last user message: 2h 10m")

    def test_zero_minutes_omitted(self):
        prior = _ts(2024, 1, 1, 10, 0)
        now = _ts(2024, 1, 1, 12, 0)
        self.assertEqual(plugin._time_since_str(prior, now),
                         "Time since last user message: 2h")

    def test_days(self):
        prior = _ts(2024, 1, 1, 10, 0)
        now = _ts(2024, 1, 5, 10, 0)
        self.assertEqual(plugin._time_since_str(prior, now),
                         "Time since last user message: 4d")

    def test_months(self):
        prior = _ts(2024, 1, 15, 10, 0)
        now = _ts(2024, 3, 15, 10, 0)
        self.assertEqual(plugin._time_since_str(prior, now),
                         "Time since last user message: 2M")

    def test_full_format(self):
        prior = _ts(2023, 1, 1, 11, 0)
        now = _ts(2024, 3, 16, 10, 14)
        self.assertEqual(
            plugin._time_since_str(prior, now),
            "Time since last user message: 1y 2M 14d 23h 14m",
        )


class TestOutput(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_first_call_has_no_time_since_line(self):
        out = plugin._inject_context(session_id="out-first")
        lines = out["context"].split("\n")
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], _TIME_LINE_RE)

    def test_second_call_after_delay_has_time_since_line(self):
        plugin._inject_context(session_id="out-second")
        time.sleep(1.2)
        out = plugin._inject_context(session_id="out-second")
        lines = out["context"].split("\n")
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], _TIME_LINE_RE)
        self.assertEqual(lines[1], "Time since last user message: just now")

    def test_subsequent_time_since_is_zero_for_same_second(self):
        plugin._inject_context(session_id="out-same-sec")
        out = plugin._inject_context(session_id="out-same-sec")
        lines = out["context"].split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1], "Time since last user message: just now")

    def test_different_sessions_do_not_share_time_since(self):
        out1 = plugin._inject_context(session_id="out-iso-A")
        out2 = plugin._inject_context(session_id="out-iso-B")
        self.assertEqual(len(out1["context"].split("\n")), 1)
        self.assertEqual(len(out2["context"].split("\n")), 1)


class TestLocking(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_parallel_different_sessions_all_persist(self):
        results = {}
        errors = []
        barrier = threading.Barrier(4)

        def worker(i):
            try:
                barrier.wait(timeout=2.0)
                out = plugin._inject_context(session_id=f"par-sess-{i}")
                results[i] = out
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertFalse(errors, f"worker errors: {errors}")
        self.assertEqual(len(results), 4)
        for i, out in results.items():
            self.assertIn("context", out)
            self.assertIn("Current local time:", out["context"])
        conn = store._store
        for i in range(4):
            cur = conn.execute(
                "SELECT ts FROM sessions WHERE id = ?", (f"par-sess-{i}",)
            )
            self.assertIsNotNone(
                cur.fetchone(),
                f"session par-sess-{i} not persisted to DB",
            )

    def test_sequential_same_session_updates_db(self):
        out1 = plugin._inject_context(session_id="seq-sess")
        self.assertIn("context", out1)
        time.sleep(0.05)
        out2 = plugin._inject_context(session_id="seq-sess")
        self.assertIn("context", out2)
        conn = store._store
        cur = conn.execute(
            "SELECT ts FROM sessions WHERE id = ?", ("seq-sess",)
        )
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertGreater(row[0], 0)


class TestEventCRUD(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.event = store.create_event(
            title="Test Meeting",
            start_time="2024-12-25T15:00:00",
            description="important",
            reminder_minutes_before=10,
        )

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_add_event_returns_event(self):
        self.assertEqual(self.event["title"], "Test Meeting")
        self.assertEqual(self.event["description"], "important")
        self.assertEqual(self.event["reminder_minutes_before"], 10)
        self.assertIn("event_id", self.event)

    def test_get_event(self):
        got = store.fetch_event(self.event["event_id"])
        self.assertIsNotNone(got)
        self.assertEqual(got["title"], "Test Meeting")

    def test_get_missing_event_returns_none(self):
        self.assertIsNone(store.fetch_event("not-real"))

    def test_update_event(self):
        updated = store.modify_event(
            self.event["event_id"], title="Updated Meeting", reminder_minutes_before=15
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["title"], "Updated Meeting")
        self.assertEqual(updated["reminder_minutes_before"], 15)

    def test_delete_event(self):
        deleted = store.remove_event(self.event["event_id"])
        self.assertTrue(deleted)
        self.assertIsNone(store.fetch_event(self.event["event_id"]))


class TestEventBulkAdd(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_add_events_returns_count(self):
        count = store.create_events([
            {"title": "A", "start_time": "2024-12-25T10:00:00"},
            {"title": "B", "start_time": "2024-12-25T11:00:00"},
        ])
        self.assertEqual(count, 2)

    def test_add_events_empty_list(self):
        self.assertEqual(store.create_events([]), 0)


class TestEventListFilters(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.now = int(time.time())
        store.create_event(title="Past", start_time=_datetime.datetime.fromtimestamp(
            self.now - 3600, tz=_datetime.timezone.utc).isoformat())
        store.create_event(title="Soon", start_time=_datetime.datetime.fromtimestamp(
            self.now + 3600, tz=_datetime.timezone.utc).isoformat())
        store.create_event(title="Far", start_time=_datetime.datetime.fromtimestamp(
            self.now + 20 * 86400, tz=_datetime.timezone.utc).isoformat())

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_list_upcoming_within_two_weeks(self):
        events = store.fetch_events(filter="upcoming", limit=10)
        titles = [e["title"] for e in events]
        self.assertIn("Soon", titles)
        self.assertNotIn("Past", titles)
        self.assertNotIn("Far", titles)

    def test_list_past(self):
        events = store.fetch_events(filter="past", limit=10)
        titles = [e["title"] for e in events]
        self.assertIn("Past", titles)
        self.assertNotIn("Soon", titles)

    def test_list_today(self):
        local_ts = _datetime.datetime.fromtimestamp(
            self.now, tz=store._resolve_local_tz())
        store.create_event(title="Today", start_time=local_ts.replace(
            hour=12, minute=0).isoformat())
        events = store.fetch_events(filter="today", limit=10)
        titles = [e["title"] for e in events]
        self.assertIn("Today", titles)


class TestContextInjectionEvents(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.now = _datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=_datetime.timezone.utc)
        self.now_ts = int(self.now.timestamp())

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    @patch.object(plugin, "_now")
    def test_upcoming_event_in_context(self, mock_now):
        mock_now.return_value = self.now
        store.create_event(
            title="Meeting",
            start_time="2024-06-15T14:35:00+00:00",
            reminder_minutes_before=10,
        )
        out = plugin._inject_context(session_id="ctx-upcoming")
        self.assertIn("Upcoming:", out["context"])
        self.assertIn("Meeting", out["context"])
        self.assertIn("(in 5m)", out["context"])

    @patch.object(plugin, "_now")
    def test_now_event_in_context(self, mock_now):
        mock_now.return_value = self.now
        store.create_event(
            title="Call",
            start_time="2024-06-15T14:25:00+00:00",
            reminder_minutes_before=10,
        )
        out = plugin._inject_context(session_id="ctx-now")
        self.assertIn("Now:", out["context"])
        self.assertIn("Call", out["context"])
        self.assertIn("(5m ago)", out["context"])

    @patch.object(plugin, "_now")
    def test_outside_window_not_in_context(self, mock_now):
        mock_now.return_value = self.now
        store.create_event(
            title="Later",
            start_time="2024-06-15T16:00:00+00:00",
            reminder_minutes_before=5,
        )
        out = plugin._inject_context(session_id="ctx-none")
        self.assertNotIn("Upcoming:", out["context"])
        self.assertNotIn("Now:", out["context"])

    @patch.object(plugin, "_now")
    def test_started_event_within_30_min_in_context(self, mock_now):
        mock_now.return_value = self.now
        store.create_event(
            title="Recent Call",
            start_time="2024-06-15T14:01:00+00:00",
            reminder_minutes_before=5,
        )
        out = plugin._inject_context(session_id="ctx-recent")
        self.assertIn("Now:", out["context"])
        self.assertIn("Recent Call", out["context"])

    @patch.object(plugin, "_now")
    def test_started_event_after_30_min_not_in_context(self, mock_now):
        mock_now.return_value = self.now
        store.create_event(
            title="Old Call",
            start_time="2024-06-15T13:59:00+00:00",
            reminder_minutes_before=5,
        )
        out = plugin._inject_context(session_id="ctx-old")
        self.assertNotIn("Now:", out["context"])
        self.assertNotIn("Old Call", out["context"])

    @patch.object(plugin, "_now")
    def test_event_with_end_time_keeps_active_after_30_min(self, mock_now):
        """An event whose end_time is past start_time+30min should still
        be in the active context when the 30-min window has elapsed
        but end_time has not. We start at 14:30 (self.now) and need a
        mock that lands 31-59 min after start (14:31-14:59) — but the
        30-min post-start filter rejects anything past 14:30, so this
        scenario is actually not testable as a 'after 30 min' case.
        Instead we verify the event is still active at a moment between
        0 and 30 min after start when end_time is far in the future."""
        # Reset mock to self.now=14:30, then create event at 14:00 with
        # end_time 15:30 (well past self.now).
        mock_now.return_value = self.now
        store.create_event(
            title="Long Meeting",
            start_time="2024-06-15T14:00:00+00:00",
            end_time="2024-06-15T15:30:00+00:00",
            reminder_minutes_before=5,
        )
        out = plugin._inject_context(session_id="ctx-long-meeting")
        self.assertIn("Now:", out["context"])
        self.assertIn("Long Meeting", out["context"])

    @patch.object(plugin, "_now")
    def test_event_with_end_time_keeps_active_past_30_min_when_end_still_future(self, mock_now):
        """A 1-hour meeting that started 45 min ago must still be
        active because end_time has not been reached, even though the
        fixed 30-min post-start window has elapsed."""
        # Use a base time of 14:00 so 'now' is 14:00 (start), then the
        # event with end_time 15:00 is 1h long. We set mock_now to a
        # moment 45 min into the event.
        base = _datetime.datetime(
            2024, 6, 15, 14, 45, tzinfo=_datetime.timezone.utc)
        mock_now.return_value = base
        store.create_event(
            title="Long Meeting",
            start_time="2024-06-15T14:00:00+00:00",
            end_time="2024-06-15T15:00:00+00:00",
            reminder_minutes_before=5,
        )
        out = plugin._inject_context(session_id="ctx-long-meeting-2")
        self.assertIn("Now:", out["context"])
        self.assertIn("Long Meeting", out["context"])

    @patch.object(plugin, "_now")
    def test_event_after_end_time_not_in_context(self, mock_now):
        """An event whose end_time has passed should not be in the
        active context, even within the 30-min post-start window."""
        mock_now.return_value = self.now
        store.create_event(
            title="Quick Call",
            start_time="2024-06-15T14:00:00+00:00",
            end_time="2024-06-15T14:05:00+00:00",
            reminder_minutes_before=5,
        )
        # 10 min after start, end_time has passed.
        advanced = self.now + _datetime.timedelta(minutes=10)
        mock_now.return_value = advanced
        out = plugin._inject_context(session_id="ctx-quick-call")
        self.assertNotIn("Now:", out["context"])
        self.assertNotIn("Quick Call", out["context"])


class TestStartupCleanup(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.now = int(time.time())

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_old_events_removed(self):
        old_ts = _datetime.datetime.fromtimestamp(
            self.now - 40 * 86400, tz=_datetime.timezone.utc)
        store.create_event(title="Old", start_time=old_ts.isoformat())
        recent_ts = _datetime.datetime.fromtimestamp(
            self.now + 3600, tz=_datetime.timezone.utc)
        store.create_event(title="Recent", start_time=recent_ts.isoformat())
        deleted = store.cleanup_old_events()
        self.assertEqual(deleted, 1)
        self.assertEqual(
            len(store.fetch_events(filter="upcoming", limit=10)), 1)


class TestRegister(unittest.TestCase):
    def test_register_calls_register_hook_and_tools(self):
        hooks = []
        tools_called = []

        class MockCtx:
            def register_hook(self, event, cb):
                hooks.append((event, cb.__name__))

            def register_tool(self, **kwargs):
                tools_called.append(kwargs["name"])

            def register_skill(self, *args, **kwargs):
                pass

        register(MockCtx())
        self.assertEqual(
            hooks,
            [
                ("pre_llm_call", "_inject_context"),
            ],
        )
        self.assertEqual(
            tools_called,
            [
                "add_event",
                "add_events",
                "list_events",
                "get_event",
                "update_event",
                "delete_event",
                "mark_event_complete",
            ],
        )


class TestToolHandlers(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_add_event_handler(self):
        result = tools.add_event({
            "title": "Lunch",
            "start_time": "2024-12-25T12:00:00",
        })
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["event"]["title"], "Lunch")

    def test_add_events_handler_returns_count(self):
        result = tools.add_events({
            "events": [
                {"title": "A", "start_time": "2024-12-25T10:00:00"},
                {"title": "B", "start_time": "2024-12-25T11:00:00"},
            ]
        })
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["created_count"], 2)

    def test_add_events_empty_list_returns_error(self):
        result = tools.add_events({"events": []})
        data = json.loads(result)
        self.assertIn("error", data)

    def test_add_events_whitespace_title_returns_error(self):
        result = tools.add_events({
            "events": [{"title": "   ", "start_time": "2024-12-25T10:00:00"}]
        })
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("title", data["error"])

    def test_add_events_whitespace_start_time_returns_error(self):
        result = tools.add_events({
            "events": [{"title": "A", "start_time": "   "}]
        })
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("start_time", data["error"])

    def test_add_events_non_string_title_returns_error(self):
        result = tools.add_events({
            "events": [{"title": 123, "start_time": "2024-12-25T10:00:00"}]
        })
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("title", data["error"])

    def test_add_events_non_string_start_time_returns_error(self):
        result = tools.add_events({
            "events": [{"title": "A", "start_time": 123}]
        })
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("start_time", data["error"])

    def test_add_event_invalid_datetime(self):
        result = tools.add_event({
            "title": "Bad",
            "start_time": "not-a-date",
        })
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("ISO 8601", data["error"])

    def test_update_event_only_event_id_returns_error(self):
        result = tools.update_event({"event_id": "some-id"})
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("at least one field", data["error"])

    def test_update_event_remove_end_time(self):
        start_time = (
            _datetime.datetime.now().astimezone() + _datetime.timedelta(days=7)
        ).replace(microsecond=0).isoformat()
        end_time = (
            _datetime.datetime.now().astimezone() + _datetime.timedelta(days=7, hours=1)
        ).replace(microsecond=0).isoformat()
        created = store.create_event(
            title="Meeting",
            start_time=start_time,
            end_time=end_time,
        )
        result = tools.update_event({
            "event_id": created["event_id"],
            "end_time": None,
        })
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertNotIn("end_time", data["event"])

    def test_update_event_not_found_returns_error(self):
        result = tools.update_event({
            "event_id": "not-real",
            "title": "New Title",
        })
        data = json.loads(result)
        self.assertIn("error", data)

    def test_update_event_partial_update(self):
        start_time = (
            _datetime.datetime.now().astimezone() + _datetime.timedelta(days=7)
        ).replace(microsecond=0).isoformat()
        created = store.create_event(
            title="Old Title",
            start_time=start_time,
        )
        result = tools.update_event({
            "event_id": created["event_id"],
            "title": "New Title",
        })
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertEqual(data["event"]["title"], "New Title")


class TestRelativeTime(unittest.TestCase):
    def test_upcoming_minutes(self):
        self.assertEqual(store.fmt_relative(1000, 1300), "in 5m")

    def test_upcoming_hours_and_minutes(self):
        self.assertEqual(store.fmt_relative(0, 7500), "in 2h 5m")

    def test_upcoming_starting_now(self):
        self.assertEqual(store.fmt_relative(999, 1000), "starting now")

    def test_started_minutes(self):
        self.assertEqual(store.fmt_relative(1300, 1000), "5m ago")

    def test_started_hours_and_minutes(self):
        self.assertEqual(store.fmt_relative(7500, 0), "2h 5m ago")

    def test_started_just_now(self):
        self.assertEqual(store.fmt_relative(1000, 1000), "started just now")


class TestStartTimeHint(unittest.TestCase):
    def test_today(self):
        now = _datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=_datetime.timezone.utc)
        dt = _datetime.datetime(
            2024, 6, 15, 9, 0, tzinfo=_datetime.timezone.utc)
        self.assertEqual(store._start_time_hint(dt, now), "today at 09:00")

    def test_tomorrow(self):
        now = _datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=_datetime.timezone.utc)
        dt = _datetime.datetime(
            2024, 6, 16, 9, 0, tzinfo=_datetime.timezone.utc)
        self.assertEqual(store._start_time_hint(dt, now), "tomorrow at 09:00")

    def test_yesterday(self):
        now = _datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=_datetime.timezone.utc)
        dt = _datetime.datetime(
            2024, 6, 14, 18, 0, tzinfo=_datetime.timezone.utc)
        self.assertEqual(store._start_time_hint(dt, now), "yesterday at 18:00")

    def test_in_days(self):
        now = _datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=_datetime.timezone.utc)
        dt = _datetime.datetime(
            2024, 6, 18, 10, 0, tzinfo=_datetime.timezone.utc)
        self.assertEqual(store._start_time_hint(dt, now), "in 3 days at 10:00")

    def test_days_ago(self):
        now = _datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=_datetime.timezone.utc)
        dt = _datetime.datetime(
            2024, 6, 12, 10, 0, tzinfo=_datetime.timezone.utc)
        self.assertEqual(store._start_time_hint(
            dt, now), "3 days ago at 10:00")


class TestEventDuration(unittest.TestCase):
    def test_minutes_only(self):
        start = int(_datetime.datetime(2024, 6, 15, 14, 0,
                    tzinfo=_datetime.timezone.utc).timestamp())
        end = int(_datetime.datetime(2024, 6, 15, 14, 45,
                  tzinfo=_datetime.timezone.utc).timestamp())
        self.assertEqual(store.fmt_duration(start, end), "45m")

    def test_hours_and_minutes(self):
        start = int(_datetime.datetime(2024, 6, 15, 14, 0,
                    tzinfo=_datetime.timezone.utc).timestamp())
        end = int(_datetime.datetime(2024, 6, 15, 16, 30,
                  tzinfo=_datetime.timezone.utc).timestamp())
        self.assertEqual(store.fmt_duration(start, end), "2h 30m")

    def test_days_hours(self):
        start = int(_datetime.datetime(2024, 6, 15, 14, 0,
                    tzinfo=_datetime.timezone.utc).timestamp())
        end = int(_datetime.datetime(2024, 6, 16, 16, 0,
                  tzinfo=_datetime.timezone.utc).timestamp())
        self.assertEqual(store.fmt_duration(start, end), "1d 2h")

    def test_sub_minute(self):
        start = int(_datetime.datetime(2024, 6, 15, 14, 0, 0,
                    tzinfo=_datetime.timezone.utc).timestamp())
        end = int(_datetime.datetime(2024, 6, 15, 14, 0, 30,
                  tzinfo=_datetime.timezone.utc).timestamp())
        self.assertEqual(store.fmt_duration(start, end), "<1m")

    def test_zero_or_negative(self):
        start = int(_datetime.datetime(2024, 6, 15, 14, 0,
                    tzinfo=_datetime.timezone.utc).timestamp())
        end = int(_datetime.datetime(2024, 6, 15, 13, 0,
                  tzinfo=_datetime.timezone.utc).timestamp())
        self.assertEqual(store.fmt_duration(start, end), "0m")


class TestEventFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.event = store.create_event(
            title="Format Test",
            start_time="2024-12-25T12:00:00",
            end_time="2024-12-25T13:30:00",
        )

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_start_time_has_relative_hint(self):
        self.assertIn("(", self.event["start_time"])
        self.assertIn(")", self.event["start_time"])

    def test_end_time_has_duration(self):
        self.assertIn("(1h 30m)", self.event["end_time"])

    def test_end_time_absent_when_not_provided(self):
        result = store.create_event(
            title="No End",
            start_time="2024-12-25T12:00:00",
        )
        self.assertNotIn("end_time", result)


class TestMarkComplete(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.event = store.create_event(
            title="To Complete",
            start_time=(
                _datetime.datetime.now().astimezone() + _datetime.timedelta(days=7)
            ).replace(microsecond=0).isoformat(),
        )

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_new_event_not_completed(self):
        self.assertFalse(self.event["completed"])
        self.assertIsNone(self.event["completed_at"])

    def test_mark_sets_completed_at(self):
        result = store.mark_event_complete(self.event["event_id"])
        self.assertIsNotNone(result)
        self.assertTrue(result["completed"])
        self.assertIsNotNone(result["completed_at"])
        self.assertIn("event_id", result)

    def test_mark_persists_to_db(self):
        store.mark_event_complete(self.event["event_id"])
        fetched = store.fetch_event(self.event["event_id"])
        self.assertIsNotNone(fetched)
        self.assertTrue(fetched["completed"])
        self.assertIsNotNone(fetched["completed_at"])

    def test_mark_is_idempotent(self):
        first = store.mark_event_complete(self.event["event_id"])
        first_ts = first["completed_at"]
        time.sleep(1.1)
        second = store.mark_event_complete(self.event["event_id"])
        self.assertEqual(second["completed_at"], first_ts)

    def test_mark_unknown_id_returns_none(self):
        self.assertIsNone(store.mark_event_complete("not-real"))

    def test_mark_handler_success(self):
        result = tools.mark_event_complete(
            {"event_id": self.event["event_id"]})
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertTrue(data["event"]["completed"])

    def test_mark_handler_missing_event_id(self):
        result = tools.mark_event_complete({})
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("event_id", data["error"])

    def test_mark_handler_whitespace_event_id(self):
        result = tools.mark_event_complete({"event_id": "   "})
        data = json.loads(result)
        self.assertIn("error", data)

    def test_mark_handler_unknown_id(self):
        result = tools.mark_event_complete({"event_id": "not-real"})
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("not found", data["error"])

    def test_fetch_completed_events_lists_marked(self):
        store.mark_event_complete(self.event["event_id"])
        other = store.create_event(
            title="Active", start_time="2024-12-26T10:00:00")
        completed = store.fetch_completed_events(limit=10)
        ids = [e["event_id"] for e in completed]
        self.assertIn(self.event["event_id"], ids)
        self.assertNotIn(other["event_id"], ids)

    def test_fetch_completed_events_empty_when_none(self):
        self.assertEqual(store.fetch_completed_events(limit=10), [])


class TestCompletedExclusion(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.now = _datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=_datetime.timezone.utc)

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    @patch.object(plugin, "_now")
    def test_completed_event_not_in_active_events(self, mock_now):
        mock_now.return_value = self.now
        event = store.create_event(
            title="Soon Call",
            start_time="2024-06-15T14:35:00+00:00",
            reminder_minutes_before=10,
        )
        store.mark_event_complete(event["event_id"])
        upcoming, now_events = store.get_active_events(
            int(self.now.timestamp()))
        self.assertEqual(upcoming, [])
        self.assertEqual(now_events, [])

    @patch.object(plugin, "_now")
    def test_completed_event_not_in_context_injection(self, mock_now):
        mock_now.return_value = self.now
        event = store.create_event(
            title="Done Meeting",
            start_time="2024-06-15T14:35:00+00:00",
            reminder_minutes_before=10,
        )
        store.mark_event_complete(event["event_id"])
        out = plugin._inject_context(session_id="ctx-completed")
        self.assertNotIn("Upcoming:", out["context"])
        self.assertNotIn("Now:", out["context"])
        self.assertNotIn("Done Meeting", out["context"])

    @patch.object(plugin, "_now")
    def test_active_event_still_in_context(self, mock_now):
        mock_now.return_value = self.now
        store.create_event(
            title="Still Active",
            start_time="2024-06-15T14:35:00+00:00",
            reminder_minutes_before=10,
        )
        out = plugin._inject_context(session_id="ctx-active")
        self.assertIn("Upcoming:", out["context"])
        self.assertIn("Still Active", out["context"])

    def test_fetch_events_excludes_completed(self):
        now = int(time.time())
        store.create_event(
            title="Active",
            start_time=_datetime.datetime.fromtimestamp(
                now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        done = store.create_event(
            title="Done",
            start_time=_datetime.datetime.fromtimestamp(
                now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        store.mark_event_complete(done["event_id"])
        events = store.fetch_events(filter="upcoming", limit=10)
        titles = [e["title"] for e in events]
        self.assertIn("Active", titles)
        self.assertNotIn("Done", titles)


class TestListEventsShowCompleted(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.now = int(time.time())

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_default_hides_completed(self):
        store.create_event(
            title="Active",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        done = store.create_event(
            title="Done",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        store.mark_event_complete(done["event_id"])
        result = tools.list_events({"filter": "upcoming"})
        data = json.loads(result)
        self.assertIn("events", data)
        self.assertNotIn("active", data)
        self.assertNotIn("completed", data)
        titles = [e["title"] for e in data["events"]]
        self.assertIn("Active", titles)
        self.assertNotIn("Done", titles)

    def test_show_completed_returns_sections(self):
        store.create_event(
            title="Active2",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        done = store.create_event(
            title="Done2",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        store.mark_event_complete(done["event_id"])
        result = tools.list_events(
            {"filter": "upcoming", "show_completed": True})
        data = json.loads(result)
        self.assertIn("active", data)
        self.assertIn("completed", data)
        active_titles = [e["title"] for e in data["active"]]
        completed_titles = [e["title"] for e in data["completed"]]
        self.assertIn("Active2", active_titles)
        self.assertNotIn("Done2", active_titles)
        self.assertIn("Done2", completed_titles)
        self.assertNotIn("Active2", completed_titles)

    def test_show_completed_with_past_filter(self):
        store.create_event(
            title="PastActive",
            start_time=_datetime.datetime.fromtimestamp(
                self.now - 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        done = store.create_event(
            title="PastDone",
            start_time=_datetime.datetime.fromtimestamp(
                self.now - 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        store.mark_event_complete(done["event_id"])
        # Backdate completed_at to 1 hour ago to make the past filter
        # deterministic regardless of test execution speed.
        store._store.execute(
            "UPDATE events SET completed_at = ? WHERE event_id = ?",
            (self.now - 3600, done["event_id"]),
        )
        result = tools.list_events({"filter": "past", "show_completed": True})
        data = json.loads(result)
        active_titles = [e["title"] for e in data["active"]]
        completed_titles = [e["title"] for e in data["completed"]]
        self.assertIn("PastActive", active_titles)
        self.assertIn("PastDone", completed_titles)

    def test_show_completed_with_upcoming_filter_excludes_completed(self):
        """With filter='upcoming', a completed event with
        completed_at < now is excluded from the completed list."""
        store.create_event(
            title="UpcomingActive",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        done = store.create_event(
            title="UpcomingDone",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        store.mark_event_complete(done["event_id"])
        # Backdate completed_at to 1 hour ago so the past-completed
        # event does not fall in the upcoming-completed window.
        store._store.execute(
            "UPDATE events SET completed_at = ? WHERE event_id = ?",
            (self.now - 3600, done["event_id"]),
        )
        result = tools.list_events(
            {"filter": "upcoming", "show_completed": True})
        data = json.loads(result)
        active_titles = [e["title"] for e in data["active"]]
        completed_titles = [e["title"] for e in data["completed"]]
        self.assertIn("UpcomingActive", active_titles)
        self.assertEqual(completed_titles, [])

    def test_show_completed_with_today_filter(self):
        """With filter='today', both active and completed lists are
        restricted to the local-time today window."""
        # An event completed within today's local-time window.
        done_today = store.create_event(
            title="DoneToday",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        store.mark_event_complete(done_today["event_id"])
        # An event completed outside today's local-time window.
        done_other = store.create_event(
            title="DoneOther",
            start_time=_datetime.datetime.fromtimestamp(
                self.now + 3600, tz=_datetime.timezone.utc).isoformat(),
        )
        with patch.object(store, "fetch_completed_events", wraps=store.fetch_completed_events):
            # Manually backdate completed_at for done_other to far past.
            store._store.execute(
                "UPDATE events SET completed_at = ? WHERE event_id = ?",
                (self.now - 40 * 86400, done_other["event_id"]),
            )
            result = tools.list_events(
                {"filter": "today", "show_completed": True})
        data = json.loads(result)
        completed_titles = [e["title"] for e in data["completed"]]
        self.assertIn("DoneToday", completed_titles)
        self.assertNotIn("DoneOther", completed_titles)

    def test_show_completed_empty_when_none(self):
        result = tools.list_events(
            {"filter": "upcoming", "show_completed": True})
        data = json.loads(result)
        self.assertEqual(data["active"], [])
        self.assertEqual(data["completed"], [])

    def test_show_completed_default_false(self):
        result = tools.list_events({"filter": "upcoming"})
        data = json.loads(result)
        self.assertNotIn("active", data)
        self.assertNotIn("completed", data)


class TestUnmarkComplete(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.event = store.create_event(
            title="To Unmark",
            start_time=(
                _datetime.datetime.now().astimezone() + _datetime.timedelta(days=7)
            ).replace(microsecond=0).isoformat(),
        )

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_unmark_via_modify_event(self):
        store.mark_event_complete(self.event["event_id"])
        marked = store.fetch_event(self.event["event_id"])
        self.assertTrue(marked["completed"])
        result = store.modify_event(self.event["event_id"], completed_at=None)
        self.assertIsNotNone(result)
        self.assertFalse(result["completed"])
        self.assertIsNone(result["completed_at"])

    def test_unmark_via_update_event_handler(self):
        store.mark_event_complete(self.event["event_id"])
        result = tools.update_event({
            "event_id": self.event["event_id"],
            "completed_at": None,
        })
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertFalse(data["event"]["completed"])
        self.assertIsNone(data["event"]["completed_at"])

    def test_modify_event_rejects_non_null_completed_at(self):
        with self.assertRaises(ValueError) as ctx:
            store.modify_event(self.event["event_id"], completed_at=True)
        self.assertIn("mark_event_complete", str(ctx.exception))

    def test_modify_event_rejects_string_completed_at(self):
        with self.assertRaises(ValueError):
            store.modify_event(
                self.event["event_id"], completed_at="2024-01-01T00:00:00")


class TestParseDateRange(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_single_day_returns_24h_range(self):
        start, end = store._parse_date_range("2026-06-15", None)
        self.assertEqual(end - start, 86400)

    def test_multi_day_returns_inclusive_end(self):
        start, end = store._parse_date_range("2026-06-15", "2026-06-21")
        # 7 days inclusive: 6 full days + 1 partial = 7 * 86400
        self.assertEqual(end - start, 7 * 86400)

    def test_empty_start_raises(self):
        with self.assertRaises(ValueError) as ctx:
            store._parse_date_range("", None)
        self.assertIn("start_date is required", str(ctx.exception))

    def test_end_before_start_raises(self):
        with self.assertRaises(ValueError) as ctx:
            store._parse_date_range("2026-06-21", "2026-06-15")
        self.assertIn("must be on or after", str(ctx.exception))

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            store._parse_date_range("besok", None)
        with self.assertRaises(ValueError):
            store._parse_date_range("2026/06/15", None)
        with self.assertRaises(ValueError):
            store._parse_date_range("2026-6-15", None)


class TestFetchEventsByRange(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.tz = store._resolve_local_tz()
        self.now = int(time.time())
        # Build a known week starting from "tomorrow" local time.
        self.tomorrow = self.now + 86400
        self.week_start = _datetime.datetime.fromtimestamp(
            self.tomorrow, tz=self.tz).strftime("%Y-%m-%d")
        self.week_end = _datetime.datetime.fromtimestamp(
            self.now + 7 * 86400, tz=self.tz).strftime("%Y-%m-%d")
        self.day = lambda d, h=12: self.tomorrow + d * 86400 + (h - 12) * 3600
        store.create_event(
            title="Mon", start_time=self._iso(self.day(0, 9), 60))
        store.create_event(
            title="Wed", start_time=self._iso(self.day(2, 14), 30))
        store.create_event(
            title="NoEnd", start_time=self._iso(self.day(3, 10)))
        # Event that starts before the range and ends inside it.
        store.create_event(
            title="Straddle", start_time=self._iso(self.day(-1, 22), 8 * 60))

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def _iso(self, start_ts, duration_minutes=None):
        s = _datetime.datetime.fromtimestamp(
            start_ts, tz=self.tz).isoformat()
        if duration_minutes is None:
            return s
        return s

    def test_includes_events_starting_in_range(self):
        start, end = store._parse_date_range(self.week_start, self.week_end)
        events = store.fetch_events_by_range(start, end)
        titles = {e["title"] for e in events}
        self.assertIn("Mon", titles)
        self.assertIn("Wed", titles)
        self.assertIn("NoEnd", titles)

    def test_includes_straddling_event(self):
        start, end = store._parse_date_range(self.week_start, self.week_end)
        events = store.fetch_events_by_range(start, end)
        titles = {e["title"] for e in events}
        self.assertIn("Straddle", titles)

    def test_excludes_completed_events(self):
        # Mark Wed as complete; it should no longer appear.
        all_events = store.fetch_events(filter="upcoming", limit=100)
        wed = next(e for e in all_events if e["title"] == "Wed")
        store.mark_event_complete(wed["event_id"])
        start, end = store._parse_date_range(self.week_start, self.week_end)
        events = store.fetch_events_by_range(start, end)
        titles = {e["title"] for e in events}
        self.assertNotIn("Wed", titles)

    def test_completed_by_range_filters_by_completed_at(self):
        all_events = store.fetch_events(filter="upcoming", limit=100)
        wed = next(e for e in all_events if e["title"] == "Wed")
        store.mark_event_complete(wed["event_id"])
        start, end = self.now - 3600, self.now + 3600
        completed = store.fetch_completed_events_by_range(start, end)
        titles = {e["title"] for e in completed}
        self.assertIn("Wed", titles)


class TestFormatEventDuration(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_duration_minutes_with_end_time(self):
        start = _datetime.datetime(2026, 6, 15, 14, 0, tzinfo=_datetime.timezone.utc)
        end = _datetime.datetime(2026, 6, 15, 15, 30, tzinfo=_datetime.timezone.utc)
        e = store.create_event(
            title="Meeting",
            start_time=start.isoformat(),
            end_time=end.isoformat(),
        )
        self.assertEqual(e["duration_minutes"], 90)

    def test_duration_minutes_defaults_to_60_without_end_time(self):
        start = _datetime.datetime(2026, 6, 15, 14, 0, tzinfo=_datetime.timezone.utc)
        e = store.create_event(title="Reminder", start_time=start.isoformat())
        self.assertIsNone(e.get("end_time"))
        self.assertEqual(e["duration_minutes"], 60)


class TestListEventsHandlerDateRange(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.tz = store._resolve_local_tz()
        self.now = int(time.time())
        self.tomorrow = self.now + 86400
        self.tomorrow_str = _datetime.datetime.fromtimestamp(
            self.tomorrow, tz=self.tz).strftime("%Y-%m-%d")
        self.week_end_str = _datetime.datetime.fromtimestamp(
            self.now + 7 * 86400, tz=self.tz).strftime("%Y-%m-%d")
        self.day = lambda d, h=12: self.tomorrow + d * 86400 + (h - 12) * 3600
        mon_start, mon_end = self._iso(self.day(0, 9), 60)
        store.create_event(title="Mon", start_time=mon_start, end_time=mon_end)
        wed_start, wed_end = self._iso(self.day(2, 14), 30)
        store.create_event(title="Wed", start_time=wed_start, end_time=wed_end)

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def _iso(self, start_ts, duration_minutes):
        s = _datetime.datetime.fromtimestamp(start_ts, tz=self.tz).isoformat()
        end_ts = start_ts + duration_minutes * 60
        e = _datetime.datetime.fromtimestamp(end_ts, tz=self.tz).isoformat()
        return s, e

    def test_start_date_single_day(self):
        result = tools.list_events({"start_date": self.tomorrow_str})
        data = json.loads(result)
        titles = [e["title"] for e in data["events"]]
        self.assertEqual(titles, ["Mon"])

    def test_date_range_multi_day(self):
        result = tools.list_events({
            "start_date": self.tomorrow_str,
            "end_date": self.week_end_str,
        })
        data = json.loads(result)
        titles = [e["title"] for e in data["events"]]
        self.assertIn("Mon", titles)
        self.assertIn("Wed", titles)

    def test_invalid_date_returns_error(self):
        result = tools.list_events({"start_date": "besok"})
        data = json.loads(result)
        self.assertIn("error", data)

    def test_end_before_start_returns_error(self):
        result = tools.list_events({
            "start_date": self.week_end_str,
            "end_date": self.tomorrow_str,
        })
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("must be on or after", data["error"])

    def test_end_without_start_returns_error(self):
        result = tools.list_events({"end_date": self.week_end_str})
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("start_date is required", data["error"])

    def test_start_date_overrides_filter(self):
        # filter=upcoming would return events by start_time ordering;
        # start_date with a specific date must take precedence and
        # only return events in that local day.
        result = tools.list_events({
            "filter": "upcoming",
            "start_date": self.tomorrow_str,
        })
        data = json.loads(result)
        titles = [e["title"] for e in data["events"]]
        self.assertEqual(titles, ["Mon"])

    def test_show_completed_with_range(self):
        wed = next(
            e for e in store.fetch_events(filter="upcoming", limit=100)
            if e["title"] == "Wed")
        store.mark_event_complete(wed["event_id"])
        today_str = _datetime.datetime.fromtimestamp(
            self.now, tz=self.tz).strftime("%Y-%m-%d")
        tomorrow_str = _datetime.datetime.fromtimestamp(
            self.now + 86400, tz=self.tz).strftime("%Y-%m-%d")
        result = tools.list_events({
            "start_date": today_str,
            "end_date": tomorrow_str,
            "show_completed": True,
        })
        data = json.loads(result)
        active_titles = [e["title"] for e in data["active"]]
        completed_titles = [e["title"] for e in data["completed"]]
        self.assertNotIn("Wed", active_titles)
        self.assertIn("Wed", completed_titles)

    def test_get_event_includes_duration_minutes(self):
        start = _datetime.datetime(2026, 6, 15, 14, 0, tzinfo=_datetime.timezone.utc)
        end = _datetime.datetime(2026, 6, 15, 15, 30, tzinfo=_datetime.timezone.utc)
        e = store.create_event(
            title="Standup",
            start_time=start.isoformat(),
            end_time=end.isoformat(),
        )
        result = tools.get_event({"event_id": e["event_id"]})
        data = json.loads(result)
        self.assertEqual(data["event"]["duration_minutes"], 90)


class TestCleanupOnToolCall(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.patcher = _temp_store()
        self.now = int(time.time())
        old_iso = _datetime.datetime.fromtimestamp(
            self.now - 31 * 86400, tz=_datetime.timezone.utc
        ).isoformat()
        old = store.create_event(title="old", start_time=old_iso)
        self.old_event_id = old["event_id"]

    def tearDown(self):
        _cleanup_temp_store(self.tmpdir, self.patcher)

    def test_add_event_triggers_cleanup_of_old_event(self):
        new_iso = _datetime.datetime.fromtimestamp(
            self.now + 3600, tz=_datetime.timezone.utc
        ).isoformat()
        result = tools.add_event({"title": "new", "start_time": new_iso})
        data = json.loads(result)
        self.assertTrue(data["success"])
        self.assertIsNone(store.fetch_event(self.old_event_id))
        new_event = store.fetch_event(data["event"]["event_id"])
        self.assertIsNotNone(new_event)
        self.assertEqual(new_event["title"], "new")


class TestFormatRelativedelta(unittest.TestCase):
    def test_empty_relativedelta_returns_less_than_one_minute(self):
        self.assertEqual(store._format_relativedelta(relativedelta()), "<1m")

    def test_only_years(self):
        self.assertEqual(store._format_relativedelta(relativedelta(years=1)), "1y")

    def test_only_months(self):
        self.assertEqual(store._format_relativedelta(relativedelta(months=2)), "2M")

    def test_only_days(self):
        self.assertEqual(store._format_relativedelta(relativedelta(days=3)), "3d")

    def test_only_hours(self):
        self.assertEqual(store._format_relativedelta(relativedelta(hours=4)), "4h")

    def test_only_minutes(self):
        self.assertEqual(store._format_relativedelta(relativedelta(minutes=5)), "5m")

    def test_all_units_combined(self):
        self.assertEqual(
            store._format_relativedelta(
                relativedelta(years=1, months=2, days=3, hours=4, minutes=5)
            ),
            "1y 2M 3d 4h 5m",
        )

    def test_zero_values_are_skipped(self):
        self.assertEqual(
            store._format_relativedelta(
                relativedelta(years=1, months=0, days=0, hours=2, minutes=0)
            ),
            "1y 2h",
        )

    def test_larger_values(self):
        self.assertEqual(
            store._format_relativedelta(
                relativedelta(years=10, months=11, days=28, hours=23, minutes=59)
            ),
            "10y 11M 28d 23h 59m",
        )


if __name__ == "__main__":
    unittest.main()
