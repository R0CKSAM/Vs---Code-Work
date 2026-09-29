"""
test_catalog.py — regression tests for every defect found in the audit.
Run:  python -m unittest test_catalog -v      (no browser or network needed)
"""
import json
import os
import tempfile
import unittest

import pandas as pd

import catalog_base as cb
import sonyliv_catalog as sl
import zee5_catalog as z5

ZURL = "https://gwapi.zee5.com/content/tvod/showbucket?bucket_id=1"
SURL = "https://apiv2.sonyliv.com/AGL/1.6/A/ENG/WEB/IN/x"


class Duration(unittest.TestCase):                               # bug 1
    def test_labels(self):
        cases = {"1h 30m": 5400, "2h 5m": 7500, "1h": 3600, "90m": 5400, "45 min": 2700,
                 "2 hrs 5 mins": 7500, "1h30m": 5400, "1:30:00": 5400, "45:30": 2730,
                 "120": 7200, "": None, None: None, "n/a": None}
        for label, want in cases.items():
            self.assertEqual(cb.secs(label), want, label)

    def test_numeric_field_is_seconds(self):
        self.assertEqual(cb.duration_to_sec(5400, None), 5400)
        self.assertEqual(cb.duration_to_sec("5400", None), 5400)
        self.assertEqual(cb.duration_to_sec(None, "1h 30m"), 5400)
        self.assertEqual(cb.duration_to_sec(0, "1h"), 0)          # 0 is a value, not "missing"


class SportDetection(unittest.TestCase):                         # bugs 2, 3
    def test_title_beats_rail(self):
        self.assertEqual(cb.detect_sport([], "Pro Kabaddi Final", "Live Cricket", "/sports/games"),
                         ("Kabaddi", "title"))

    def test_genre_beats_rail(self):
        self.assertEqual(cb.detect_sport(["Football"], "Big clash", "Live Cricket", "p"),
                         ("Football", "genre"))

    def test_rail_used_when_nothing_else(self):
        self.assertEqual(cb.detect_sport([], "Highlights", "Live Cricket", "p"), ("Cricket", "rail"))

    def test_no_substring_false_positives(self):
        for t in ["Emma Raducanu interview", "Summary highlights", "Shooting Stars comedy",
                  "Racing Rani drama", "half1 show", "Prime Time"]:
            self.assertEqual(cb.detect_sport([], t, None, None), (None, None), t)

    def test_genre_only_terms(self):
        self.assertEqual(cb.detect_sport(["Shooting"], "Event", None, None), ("Shooting", "genre"))

    def test_canonical_names(self):
        self.assertEqual(cb.detect_sport([], "Kho-Kho League", None, None)[0], "Kho Kho")
        self.assertEqual(cb.detect_sport([], "Kho Kho League", None, None)[0], "Kho Kho")
        self.assertEqual(cb.detect_sport([], "UFC 300", None, None)[0], "MMA")

    def test_opaque_section_ignored(self):
        self.assertEqual(cb.detect_sport([], "Show", None, None, section="ab-f1-cd"), (None, None))
        self.assertEqual(cb.detect_sport([], "Show", None, None, section="/sports/tennis")[0], "Tennis")


class Access(unittest.TestCase):                                 # bugs 4, 5
    def test_unknown_stays_unknown(self):
        self.assertEqual(cb.parse_access(), (None, None, None))
        r = z5._row({"id": 1, "title": "x"}, None, "p", None)
        self.assertIsNone(r["is_free"]); self.assertIsNone(r["subscription_required"])

    def test_modes(self):
        self.assertEqual(cb.parse_access(mode="FREE"), (True, False, False))
        self.assertEqual(cb.parse_access(mode="avod"), (True, False, False))
        self.assertEqual(cb.parse_access(mode="premium"), (False, True, False))
        self.assertEqual(cb.parse_access(mode="TVOD"), (False, False, True))
        self.assertEqual(cb.parse_access(free_flag=False), (False, True, False))
        self.assertEqual(cb.parse_access(free_flag="true"), (True, False, False))
        self.assertEqual(cb.parse_access(free_flag=0), (False, True, False))

    def test_sonyliv_null_access_type_no_crash(self):
        r = sl._row({"contentId": 1, "title": "T", "accessType": None}, "R", "p", None)
        self.assertIsNone(r["is_free"])


class Timestamps(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(cb.to_utc_iso(1700000000), "2023-11-14T22:13:20Z")
        self.assertEqual(cb.to_utc_iso(1700000000000), "2023-11-14T22:13:20Z")
        self.assertEqual(cb.to_utc_iso("2023-11-15T03:43:20+05:30"), "2023-11-14T22:13:20Z")
        self.assertEqual(cb.to_utc_iso("2023-11-15 03:43:20"), "2023-11-15 03:43:20")  # tz unknown → raw
        self.assertIsNone(cb.to_utc_iso(None))


class ZeeParser(unittest.TestCase):
    def setUp(self):
        self.p = z5.ZEE5Parser()

    def test_page_label_is_browsed_page(self):                   # bug 6
        self.p.current_page = "/sports/games"
        self.p.parse(ZURL, {"bucket_response": [{"bucket_name": "Live", "bucket_id": "b",
                                                 "items": [{"id": "a", "title": "T"}]}]})
        self.assertEqual(self.p.rows[0]["page"], "/sports/games")
        self.assertEqual(self.p.rows[0]["found_in"], "/sports/games > Live")

    def test_fallback_label_is_marked_api(self):
        self.p.parse(ZURL, {"bucket_response": [{"bucket_name": "L", "items": [{"id": "a", "title": "T"}]}]})
        self.assertTrue(self.p.rows[0]["page"].startswith("api:"))

    def test_list_payload_no_crash(self):                        # bug 8
        self.p.parse("https://gwapi.zee5.com/x", [{"id": 1, "title": "A"}, "junk", 5])
        self.assertEqual(len(self.p.rows), 1)

    def test_full_row(self):
        self.p.current_page = "/sports/games"
        self.p.parse(ZURL, {"bucket_response": [{"bucket_name": "Live Cricket", "bucket_id": "b1", "items": [
            {"id": "m1", "title": "India vs Australia", "content_type": "match",
             "genres": [{"id": "1", "value": "Cricket"}], "subscription_type": "premium",
             "teams": [{"name": "India"}, {"name": "Australia"}],
             "languages": ["Hindi", "English"], "duration": 5400, "season": 0,
             "start_time": 1700000000},
            {"id": "m2", "title": "Kabaddi clip", "content_type": "clip", "genres": "Kabaddi, Sports",
             "subscription_type": "FREE"},
            {"id": "m3", "title": "Unknown", "content_type": "video"},
        ]}]})
        r = {x["content_id"]: x for x in self.p.rows}
        self.assertEqual(r["m1"]["teams"], "India vs Australia")
        self.assertEqual(r["m1"]["sport"], "Cricket")
        self.assertEqual((r["m1"]["is_free"], r["m1"]["subscription_required"]), (False, True))
        self.assertEqual(r["m1"]["duration_sec"], 5400)
        self.assertEqual(r["m1"]["season_number"], 0)              # 0 preserved
        self.assertIsNone(r["m1"]["original_language"])            # not guessed
        self.assertEqual(r["m1"]["language_count"], 2)
        self.assertEqual(r["m1"]["match_start_utc"], "2023-11-14T22:13:20Z")
        self.assertEqual(r["m2"]["sport"], "Kabaddi")              # not Cricket (rail)
        self.assertEqual(r["m2"]["sport_source"], "genre")
        self.assertIsNone(r["m3"]["is_free"])

    def test_same_title_two_rails_kept_separately(self):
        for rail in ("A", "B"):
            self.p.parse(ZURL, {"bucket_response": [{"bucket_name": rail,
                                                     "items": [{"id": "x", "title": "T"}]}]})
        self.assertEqual(len(self.p.rows), 2)

    def test_slug_discovery_is_restricted(self):                 # bug 9
        self.p.maybe_slug("/sports/cricket?x=1")
        self.p.maybe_slug("/api/v1/track?id=3")
        self.p.maybe_slug("https://evil.example/sports/x")
        self.assertEqual(self.p.slugs, {"/sports/cricket"})


class SonyParser(unittest.TestCase):
    def test_containers_nested_and_flat(self):
        p = sl.SonyLIVParser()
        p.current_page = "/custompage/sports-2245"
        p.parse(SURL, {"resultObj": {"containers": [{
            "title": "Football Rail", "uri": "/sports/football",
            "assets": {"items": [
                {"contentId": 1, "title": "Cricket match", "contentType": "MATCH", "isFreeContent": True},
                {"contentId": 2, "title": "Serie A", "contentType": "MATCH", "accessType": None},
                {"contentId": 3, "title": "Paid", "contentType": "LIVE", "accessType": "PREMIUM"}]},
            "containers": [{"title": "Nested", "items": [{"contentId": 4, "title": "Tennis Open"}]}],
        }]}})
        r = {x["content_id"]: x for x in p.rows}
        self.assertEqual(len(r), 4)
        self.assertEqual(r["1"]["sport"], "Cricket")               # title beats rail
        self.assertEqual(r["2"]["sport"], "Football")              # Serie A
        self.assertTrue(r["1"]["is_free"]); self.assertFalse(r["1"]["subscription_required"])
        self.assertIsNone(r["2"]["is_free"])
        self.assertTrue(r["3"]["is_live"]); self.assertTrue(r["3"]["subscription_required"])
        self.assertEqual(r["4"]["rail"], "Nested")
        self.assertIn("/sports/football", p.slugs)

    def test_bad_payloads(self):
        p = sl.SonyLIVParser()
        for d in (None, "x", 5, [], {}, {"resultObj": {"containers": "no"}}, [None, 3]):
            p.parse(SURL, d)
        self.assertEqual(p.rows, [])
        p.parse("https://other.com/x", {"resultObj": {"items": [{"contentId": 1, "title": "T"}]}})
        self.assertEqual(p.rows, [])                                # non-sonyliv url ignored


class SaveAndReparse(unittest.TestCase):
    def test_save_types_and_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            rows = [z5._row({"id": "a", "title": "T", "subscription_type": "free", "duration": 60,
                             "year": "2024"}, "R", "p", None)] * 2
            df = cb.save(rows, out, cb.COMMON_COLUMNS)
            self.assertEqual(len(df), 1)
            back = pd.read_csv(out)
            self.assertEqual(list(back.columns), cb.COMMON_COLUMNS)
            self.assertEqual(int(back.loc[0, "duration_sec"]), 60)
            self.assertTrue(bool(back.loc[0, "is_free"]))
            self.assertFalse(bool(back.loc[0, "subscription_required"]))

    def test_unknown_access_is_blank_in_csv(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            cb.save([z5._row({"id": "a", "title": "T"}, "R", "p", None)], out)
            back = pd.read_csv(out)
            self.assertTrue(pd.isna(back.loc[0, "is_free"]))
            self.assertTrue(pd.isna(back.loc[0, "subscription_required"]))

    def test_empty_save_warns_and_writes_header(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            df = cb.save([], out, platform="ZEE5")
            self.assertTrue(df.empty)
            self.assertEqual(list(pd.read_csv(out).columns), cb.COMMON_COLUMNS)

    def test_reparse_roundtrip_keeps_page_and_survives_junk(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "r.jsonl")
            with open(raw, "w") as f:
                f.write(json.dumps({"url": ZURL, "page": "/sports/games", "data": {
                    "bucket_response": [{"bucket_name": "R", "items": [{"id": "a", "title": "T"}]}]}}) + "\n")
                f.write("not json\n\n")
                f.write(json.dumps({"url": ZURL, "data": [1, 2]}) + "\n")
            df = z5.parse_file(raw, os.path.join(d, "o.csv"))
            self.assertEqual(len(df), 1)
            self.assertEqual(df.loc[0, "page"], "/sports/games")

    def test_empty_raw_is_reported_not_crashing(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "r.jsonl"); open(raw, "w").close()
            self.assertTrue(z5.parse_file(raw, os.path.join(d, "o.csv")).empty)


class FakeReq:  resource_type = "xhr"
class FakeResp:
    def __init__(self, data, ct="application/json", status=200):
        self._d, self.headers, self.status = data, {"content-type": ct}, status
        self.url, self.request = "https://gwapi.zee5.com/a", FakeReq()
    def json(self):
        if self._d is ValueError: raise ValueError("no")
        return self._d


class BrowserHandler(unittest.TestCase):                         # bugs 7, overwrite
    def test_counts_json_and_records_page(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "r.jsonl"); got = []
            b = cb.Browser(lambda u, x: got.append(x), raw_path=raw)
            b.current_page = "/live"
            b._handle(FakeResp({"a": 1}))
            b._handle(FakeResp("<html>", ct="text/html"))          # ignored (still xhr → json() fails? returns str)
            b.close()
            self.assertGreaterEqual(b.n_json, 1)                    # scroll-idle signal now moves
            rec = json.loads(open(raw).readline())
            self.assertEqual(rec["page"], "/live")

    def test_handler_errors_are_counted(self):
        def boom(u, d): raise RuntimeError("x")
        b = cb.Browser(boom); b._handle(FakeResp({"a": 1}))
        self.assertEqual(b.n_errors, 1)

    def test_overwrite_really_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "r.jsonl"); open(raw, "w").write("old\n")
            cb.Browser(lambda u, x: None, raw_path=raw, append=False).close()
            self.assertEqual(open(raw).read(), "")
            open(raw, "w").write("old\n")
            cb.Browser(lambda u, x: None, raw_path=raw, append=True).close()
            self.assertEqual(open(raw).read(), "old\n")


class BlockDetection(unittest.TestCase):
    def test_403_on_document_counts_as_block(self):
        class DocReq: resource_type = "document"
        b = cb.Browser(lambda u, x: None)
        r = FakeResp({"a": 1}, ct="text/html", status=403); r.request = DocReq()
        b._handle(r)
        self.assertEqual(b.blocked_docs, 1)
        r2 = FakeResp({"a": 1}, status=403)                  # an xhr 403 is not a page block
        b._handle(r2)
        self.assertEqual(b.blocked_docs, 1)

    def test_visible_by_default(self):
        import inspect
        for mod in (z5, sl):
            sig = inspect.signature(mod.crawl)
            self.assertTrue(sig.parameters["headed"].default)


class HostFilteringAndDiscovery(unittest.TestCase):
    """Regression for the first real run: config/plan/ad/tracker JSON produced 344 junk rows per page."""
    PLANS = [{"id": f"p{i}", "title": f"Plan {i}"} for i in range(344)]

    def test_non_content_hosts_ignored(self):
        p = z5.ZEE5Parser(); p.current_page = "/sports/games"
        for u in ("https://subscriptionapiv2.zee5.com/v1/purchaseplan?x=1",
                  "https://stcf-prod.zee5.com/prod/pwa/remote/menu.json",
                  "https://cerberus.zee5.com/cerberus/platform/web_app/v2/config",
                  "https://spapi.zee5.com/singlePlayback/displayAds/v3",
                  "https://api-js.mixpanel.com/track/?domain=zee5.com",      # 'zee5' only in query
                  "https://gumi.criteo.com/sid/json?domain=zee5.com&topUrl=www.zee5.com"):
            p.parse(u, self.PLANS)
        self.assertEqual(p.rows, [])

    def test_content_hosts_still_parsed(self):
        p = z5.ZEE5Parser()
        p.parse("https://artemis.zee5.com/artemis/apq/web_app/IN/CCQ/x", [{"id": "a", "title": "T"}])
        p.parse("https://www.zee5.com/_next/data/v/en/sports/games.json", [{"id": "b", "title": "T2"}])
        self.assertEqual(len(p.rows), 2)

    def test_raw_filter_drops_trackers_before_counting(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "r.jsonl"); got = []
            b = cb.Browser(lambda u, x: got.append(u), raw_path=raw, raw_filter=z5.is_zee5_host)
            r = FakeResp({"a": 1}); r.url = "https://api-js.mixpanel.com/track/"
            b._handle(r)
            self.assertEqual((b.n_json, got), (0, []))       # tracker can't keep scrolling alive
            ok = FakeResp({"a": 1}); ok.url = "https://stcf-prod.zee5.com/x.json"
            b._handle(ok); b.close()
            self.assertEqual(b.n_json, 1)                     # zee5 config still kept in raw for inspection

    def test_slug_depth_and_locale(self):
        p = cb.BaseParser()
        for h in ("/sports/games", "/en/sports/cricket", "/sports/games/live-streaming/0-6-4z1/usn-vs-tt/0-1",
                  "/movies", "/sports-games/kabaddi/"):
            p.maybe_slug(h)
        self.assertEqual(p.slugs, {"/sports/games", "/en/sports/cricket", "/sports-games/kabaddi"})

    def test_inspector_flags_junk_endpoint(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "r.jsonl")
            with open(raw, "w") as f:
                f.write(json.dumps({"url": "https://www.zee5.com/x/artemis", "page": "/sports/games",
                                    "data": [{"id": "m", "title": "Match"}] * 2}) + "\n")
                f.write(json.dumps({"url": "https://subscriptionapiv2.zee5.com/v1/purchaseplan",
                                    "page": "/sports/games", "data": self.PLANS}) + "\n")
            out = subprocess.run([sys.executable, "inspect_raw.py", raw], capture_output=True,
                                 text=True, cwd=os.path.dirname(os.path.abspath(__file__))).stdout
            self.assertIn("subscriptionapiv2.zee5.com/v1/purchaseplan", out)
            self.assertIn("rows_from_current_parser=0", out)     # current parser ignores it
            self.assertIn("item list: $", out)


if __name__ == "__main__":
    unittest.main()
