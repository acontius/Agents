"""Tests for retrieval filters and text search."""

from datetime import date

from app.reports.retrieval import (
    get_person_activity,
    get_project_activity,
    get_report_by_id,
    search_reports,
)


def test_search_by_person(db_session, sample_reports):
    results = search_reports(db_session, person="Amin")
    assert len(results) == 2
    assert all(r.person == "Amin" for r in results)


def test_search_by_date_range(db_session, sample_reports):
    results = search_reports(
        db_session,
        date_from=date(2026, 9, 21),
        date_to=date(2026, 9, 21),
    )
    assert len(results) == 2


def test_text_search(db_session, sample_reports):
    results = search_reports(db_session, text_query="OpenRouter")
    assert len(results) == 1
    assert "OpenRouter" in (results[0].raw_text or "")


def test_text_search_project(db_session, sample_reports):
    results = search_reports(db_session, text_query="Vulnerability")
    assert len(results) == 1
    assert results[0].person == "Amin"


def test_get_report_by_id(db_session, sample_reports):
    rid = sample_reports[0].id
    r = get_report_by_id(db_session, rid)
    assert r is not None
    assert r.id == rid


def test_get_report_by_id_missing(db_session, sample_reports):
    assert get_report_by_id(db_session, 99999) is None


def test_get_project_activity(db_session, sample_reports):
    results = get_project_activity(db_session, "Tool Calling")
    assert len(results) >= 1


def test_combined_filters(db_session, sample_reports):
    results = search_reports(
        db_session,
        person="Amin",
        date_from=date(2026, 9, 20),
        date_to=date(2026, 9, 20),
        text_query="Agentic",
    )
    assert len(results) == 1
