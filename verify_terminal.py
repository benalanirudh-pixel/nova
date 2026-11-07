"""Headless smoke-test for Nova Terminal — run with offscreen Qt platform."""
import os, sys, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

results = []

def check(label, fn):
    try:
        fn()
        results.append(f"PASS  {label}")
    except Exception as exc:
        results.append(f"FAIL  {label}: {exc}")
        traceback.print_exc()

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

# 1. main window
def _make_window():
    global w
    from terminal.main_window import NovaTerminal
    w = NovaTerminal()
    w.show()
check("main_window import + show", _make_window)

# 2-6. force-create each page
page_names = ["MarketOverviewPage","StockAnalysisPage","InstitutionalPage","MarketLabPage","NovaAIPage"]
for idx in range(5):
    def _page(i=idx):
        w._ensure_page(i)
        pg = w._pages.widget(i)
        assert pg is not None
        assert type(pg).__name__ != "QLabel", f"page {i} is still a placeholder QLabel"
    check(f"page {idx} ({page_names[idx]})", _page)

# 7. processEvents (no crash)
def _events():
    app.processEvents()
check("processEvents", _events)

# write results to file so we can read them even without stdout
out_path = os.path.join(os.path.dirname(__file__), "verify_out.txt")
with open(out_path, "w") as f:
    f.write("\n".join(results) + "\n")

fails = [r for r in results if r.startswith("FAIL")]
sys.exit(1 if fails else 0)
