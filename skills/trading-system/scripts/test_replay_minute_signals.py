#!/usr/bin/env python3

import unittest

import replay_minute_signals as replay


class ReplayMinuteSignalsTest(unittest.TestCase):
    def test_dedupe_by_code_keeps_one_row(self):
        rows = [
            {"code": "002371", "name": "北方华创"},
            {"code": "002371", "name": "北方华创"},
        ]

        self.assertEqual(list(replay.dedupe_by_code(rows)), ["002371"])

    def test_market_candidates_are_main_board_and_label_independent(self):
        limit_rows = [
            {
                "code": "002371",
                "name": "北方华创",
                "business": "组装生产集成电路设备",
                "concepts": ["华为海思"],
            },
            {"code": "300223", "name": "北京君正"},
        ]

        candidates = replay.build_market_candidates(limit_rows, [])

        self.assertEqual(set(candidates), {"002371"})
        self.assertIn("集成电路设备", candidates["002371"]["business"])

    def test_high_amount_acceleration_and_limit_emit_attention_events(self):
        history = [1.0] * 10 + [10.0]

        events = replay.candidate_events("002371", history, 5_000_000_000, 1_000_000_000)
        event_names = {event[0] for event in events}

        self.assertIn("10m_acceleration", event_names)
        self.assertIn("deep_reversal", event_names)
        self.assertIn("first_limit", event_names)

    def test_low_amount_move_does_not_emit(self):
        events = replay.candidate_events(
            "002371", [1.0] * 10 + [10.0], 900_000_000, 1_000_000_000
        )

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
