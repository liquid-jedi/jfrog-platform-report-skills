import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("export_report_pdfs", ROOT / "scripts" / "export_report_pdfs.py")
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


class PdfExportTests(unittest.TestCase):
    def test_export_modes_are_encoded_in_file_url(self):
        with tempfile.TemporaryDirectory() as temp:
            html = Path(temp) / "report.html"
            html.write_text("<html></html>", encoding="utf-8")
            output = Path(temp) / "executive-report.pdf"
            command = EXPORTER.export_command("chrome", html, output, "executive")
        self.assertTrue(command[-1].endswith("report.html?export=executive"))
        self.assertIn(f"--print-to-pdf={output.resolve()}", command)

    def test_template_has_dedicated_light_print_presentation(self):
        template = (ROOT / "assets" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('body[data-export-mode="executive"] #executive', template)
        self.assertIn("background:#fff!important", template)
        self.assertIn("new URLSearchParams(location.search).get('export')", template)


if __name__ == "__main__":
    unittest.main()
