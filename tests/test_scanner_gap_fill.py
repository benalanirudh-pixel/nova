import unittest

import pandas as pd

from analysis.data import market_scanner as ms


def frame(days, closes, tz="Asia/Kolkata"):
    idx = pd.DatetimeIndex(pd.to_datetime(days)).tz_localize(tz)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": 1000.0}, index=idx)


class TestGapFill(unittest.TestCase):
    STORE = pd.DataFrame({"Open": [100.0, 102.0, 95.0], "High": [100.0, 102.0, 95.0], "Low": [100.0, 102.0, 95.0],
                          "Close": [100.0, 102.0, 95.0], "Volume": [5e5, 5e5, 5e5]},
                         index=pd.DatetimeIndex(pd.to_datetime(["2026-11-13", "2026-11-16", "2026-11-17"])))

    def test_missing_completed_session_restores_true_one_day_move(self):
        yahoo = frame(["2026-11-13", "2026-11-16", "2026-11-18"], [100.0, 102.0, 91.0])  # 17 Nov lagging at Yahoo
        self.assertAlmostEqual(ms.calculate_return(yahoo["Close"], 1), -10.78, places=2)  # really a 2-day move
        fixed, n = ms.fill_missing_sessions(yahoo, self.STORE)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(ms.calculate_return(fixed["Close"], 1), (91 / 95 - 1) * 100, places=6)
        self.assertEqual(str(fixed.index.tz), "Asia/Kolkata")

    def test_complete_frame_untouched(self):
        yahoo = frame(["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"], [100.0, 102.0, 95.0, 91.0])
        fixed, n = ms.fill_missing_sessions(yahoo, self.STORE)
        self.assertEqual(n, 0)
        self.assertIs(fixed, yahoo)

    def test_adjustment_mismatch_and_weekend_sessions_skipped(self):
        store = self.STORE.copy()
        store.loc[pd.Timestamp("2026-11-17"), "Close"] = 40.0          # unadjusted split-like jump: do not trust
        store.loc[pd.Timestamp("2026-11-08")] = [99.0, 99.0, 99.0, 99.0, 1e5]  # Sunday Muhurat session
        yahoo = frame(["2026-11-06", "2026-11-13", "2026-11-16", "2026-11-18"], [98.0, 100.0, 102.0, 91.0])
        self.assertEqual(ms.fill_missing_sessions(yahoo, store.sort_index())[1], 0)

    def test_no_store_data(self):
        yahoo = frame(["2026-11-16", "2026-11-18"], [102.0, 91.0])
        self.assertEqual(ms.fill_missing_sessions(yahoo, None)[1], 0)



class TestSectorClassifierColumns(unittest.TestCase):
    def test_parser_source_columns_are_accepted(self):
        # sector_classification.parse_primary_html returns source_* names; this crashed every scan from 2026-11-17
        from analysis.data import sector_engine as se
        rows = pd.DataFrame([{"source_symbol": "NEWCO", "source_company_name": "New Co Ltd", "macro_sector": "Energy",
                              "sector": "Oil", "industry": "Refining", "basic_industry": "Refineries"}])
        out = se.canonicalize_primary_rows(rows)
        self.assertEqual(out.iloc[0]["company_name"], "New Co Ltd")
        self.assertEqual(out.iloc[0]["symbol"], "NEWCO")


class TestStaleSectorWarning(unittest.TestCase):
    def test_warns_only_when_sector_file_is_not_today(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from web.api import market_updates as mu
        now = datetime(2026, 11, 19, 12, 21, tzinfo=ZoneInfo("Asia/Kolkata"))
        old = {"sector_file": "C:/x/sector_scan_20261117_103552.csv"}
        self.assertEqual(mu.stale_sector_warning(old, now), "⚠ Sector data is from 17-Nov (sector refresh failed)")
        self.assertIsNone(mu.stale_sector_warning({"sector_file": "sector_scan_20261119_120834.csv"}, now))
        self.assertIn("⚠ Sector data is from 17-Nov", mu.rescan_text(old, now))

if __name__ == "__main__":
    unittest.main()
