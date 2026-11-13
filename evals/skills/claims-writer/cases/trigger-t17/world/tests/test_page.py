from src.reports.page import report_page


def test_title():
    assert report_page([])["title"] == "Reports"
