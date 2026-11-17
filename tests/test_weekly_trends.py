import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRENDS = load("weekly_trends", ROOT / "scripts" / "apply_weekly_trends.py")
RENDER = load("render_weekly", ROOT / "scripts" / "render_report.py")


def report(start, end, critical, users, completeness="complete"):
    def metric(mid, label, value, unit):
        return {"id": mid, "label": label, "value": value, "unit": unit,
                "classification": "observed", "source": "test", "formula": "count"}
    return {
        "meta": {"period_start": start, "period_end": end, "period_completeness": completeness},
        "xray": {"metrics": [metric("xray-critical-findings", "Critical violations", critical, "findings")]},
        "curation": {"metrics": [metric("curation-users", "Curation unique users", users, "identities")]},
    }


class WeeklyTrendTests(unittest.TestCase):
    def test_builds_week_on_week_series_for_calendar_month(self):
        first = report("2026-11-02T00:00:00Z", "2026-11-08T23:59:59Z", 10, 20)
        second = report("2026-11-09T00:00:00Z", "2026-11-15T23:59:59Z", 15, 22)
        value = TRENDS.inject(second, [(Path("week-1"), first)], "2026-11", "UTC")
        series = {item["id"]: item for item in value["weekly_trend"]["series"]}
        self.assertEqual([point["value"] for point in series["xray-critical-findings"]["points"]], [10, 15])
        self.assertEqual(series["xray-critical-findings"]["latest_change_percent"], 50.0)
        self.assertEqual(series["xray-critical-findings"]["polarity"], "lower_is_better")

    def test_excludes_future_archives_and_current_posture_metrics(self):
        current = report("2026-11-02T00:00:00Z", "2026-11-08T23:59:59Z", 10, 20)
        current["access_governance"] = {"metrics": [{
            "id": "access-expiring-7d", "label": "Tokens expiring", "value": 4,
            "unit": "tokens", "classification": "observed", "source": "current inventory",
            "formula": "count",
        }]}
        future = report("2026-11-09T00:00:00Z", "2026-11-15T23:59:59Z", 15, 22)
        value = TRENDS.inject(current, [(Path("future"), future)], "2026-11", "UTC")
        self.assertEqual([week["period_key"] for week in value["weekly_trend"]["weeks"]], ["2026-11-08"])
        self.assertNotIn("access-expiring-7d", {item["id"] for item in value["weekly_trend"]["series"]})

    def test_week_to_date_is_not_compared_with_complete_week(self):
        complete = report("2026-11-09T00:00:00Z", "2026-11-15T23:59:59Z", 10, 20)
        partial = report("2026-11-16T00:00:00Z", "2026-11-17T08:40:00Z", 4, 8, "week_to_date")
        value = TRENDS.inject(partial, [(Path("complete"), complete)], "2026-11", "UTC")
        trend = value["weekly_trend"]
        self.assertFalse(trend["current_period_comparable"])
        self.assertEqual([week["period_key"] for week in trend["weeks"]], ["2026-11-15"])
        self.assertEqual(trend["series"], [])
        self.assertIn("excluded from WoW", trend["interpretation"])

    def test_bad_metric_value_renders_red_semantics(self):
        html = RENDER.card({"id": "xray-critical-findings", "classification": "observed",
                            "label": "Critical findings", "value": 2, "unit": "findings",
                            "source": "test", "formula": "count"})
        self.assertIn("risk-bad", html)

    def test_not_malicious_is_not_colored_as_bad(self):
        self.assertFalse(RENDER.is_adverse_text("Not malicious"))
        self.assertTrue(RENDER.is_adverse_text("Malicious"))

    def test_contextual_increase_stays_neutral(self):
        model = {"series": [{"id": "curation-blocked", "label": "Blocked", "polarity": "contextual",
                              "latest_change_percent": 20.0,
                              "points": [{"period_key": "a", "label": "W1", "value": 10}, {"period_key": "b", "label": "W2", "value": 12}]}]}
        html = RENDER.weekly_trend_panel(model)
        self.assertIn("series-delta neutral", html)

    def test_negative_change_uses_metric_polarity(self):
        improving = {"series": [{"id": "xray-critical-findings", "label": "Critical", "polarity": "lower_is_better",
                                  "latest_change_percent": -25.0,
                                  "points": [{"label": "W1", "value": 20}, {"label": "W2", "value": 15}]}]}
        declining = {"series": [{"id": "curation-users", "label": "Users", "polarity": "higher_is_better",
                                  "latest_change_percent": -25.0,
                                  "points": [{"label": "W1", "value": 20}, {"label": "W2", "value": 15}]}]}
        self.assertIn("series-card trend-good", RENDER.weekly_trend_panel(improving))
        self.assertIn("series-delta good", RENDER.weekly_trend_panel(improving))
        self.assertIn("series-card trend-bad", RENDER.weekly_trend_panel(declining))
        self.assertIn("series-delta bad", RENDER.weekly_trend_panel(declining))

    def test_template_removes_audience_from_header(self):
        template = (ROOT / "assets" / "dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("Audience:", template)
        self.assertNotIn("REPORT_PERSONA", template)
        self.assertIn("<!--REPORT_FOOTER-->", template)
        self.assertNotIn("<!--REPORT_PERSONA-->", template)

    def test_report_sections_are_single_row_tabs(self):
        template = (ROOT / "assets" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn(".nav-links{display:flex;align-items:stretch;flex-wrap:nowrap", template)
        nav_css = template.split(".nav-links{", 1)[1].split("}", 1)[0]
        self.assertNotIn("overflow", nav_css)
        self.assertNotIn("scrollbar", nav_css)
        self.assertIn(".section-nav a:hover,.section-nav a.active", template)
        self.assertIn("IntersectionObserver", template)


if __name__ == "__main__":
    unittest.main()
