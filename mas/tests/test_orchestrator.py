"""
Тесты для orchestrator.run_collection.

Unit-тесты: подставные агенты.
Integration-тесты: полный проход с mock-данными.
"""
import pytest
from unittest.mock import patch

from mas.price_drivers_collection.orchestrator import run_collection


# ═══════════════════════════════════════════════════════════════════
# UNIT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRunCollectionStructure:
    """Проверка структуры возвращаемых данных."""

    def test_returns_dict(self, container_with_success_agent, mock_tickers_data):
        results = run_collection(container_with_success_agent, mock_tickers_data)
        assert isinstance(results, dict)

    def test_keys_match_tickers(self, container_with_success_agent, mock_tickers_data):
        results = run_collection(container_with_success_agent, mock_tickers_data)
        expected_tickers = {t["ticker"] for t in mock_tickers_data}
        assert set(results.keys()) == expected_tickers

    def test_result_counts_match(self, container_with_success_agent, mock_tickers_data):
        results = run_collection(container_with_success_agent, mock_tickers_data)
        for ticker_data in mock_tickers_data:
            ticker = ticker_data["ticker"]
            assert len(results[ticker]) == len(ticker_data["records"])


class TestRunCollectionSuccess:
    """Все агенты успешны."""

    def test_all_results_successful(self, container_with_success_agent, mock_tickers_data):
        results = run_collection(container_with_success_agent, mock_tickers_data)
        for ticker, records in results.items():
            for r in records:
                assert r["success"] is True, f"Failed: {ticker}/{r['year']}"


class TestRunCollectionFailure:
    """Все агенты падают."""

    def test_all_results_failed(self, container_with_fail_agent, mock_tickers_data):
        results = run_collection(container_with_fail_agent, mock_tickers_data)
        for ticker, records in results.items():
            for r in records:
                assert r["success"] is False

    def test_processes_all_tickers_despite_failures(self, container_with_fail_agent, mock_tickers_data):
        """Оркестратор не останавливается при ошибках."""
        results = run_collection(container_with_fail_agent, mock_tickers_data)
        assert len(results) == len(mock_tickers_data)


class TestRunCollectionPartialFailure:
    """Смешанные результаты."""

    def test_mixed_results_counted_correctly(self, container_with_partial_fail_agent):
        tickers_data = [
            {
                "ticker": "MIX",
                "records": [
                    {"year": 2019, "price": 100, "dividend": 2, "yoy_change": 5},  # success
                    {"year": 2020, "price": 110, "dividend": 2, "yoy_change": 5},  # fail
                    {"year": 2021, "price": 120, "dividend": 2, "yoy_change": 5},  # success
                ],
            },
        ]
        results = run_collection(container_with_partial_fail_agent, tickers_data)

        mix_results = results["MIX"]
        successes = [r for r in mix_results if r["success"]]
        failures = [r for r in mix_results if not r["success"]]

        assert len(successes) == 2
        assert len(failures) == 1


class TestRunCollectionEdgeCases:
    """Граничные случаи."""

    def test_empty_tickers_list(self, container_with_success_agent):
        results = run_collection(container_with_success_agent, [])
        assert results == {}

    def test_ticker_with_no_records(self, container_with_success_agent, empty_records_ticker):
        results = run_collection(container_with_success_agent, [empty_records_ticker])
        assert results["EMPTY"] == []

    def test_single_ticker_single_record(self, container_with_success_agent):
        tickers_data = [
            {
                "ticker": "ONE",
                "records": [{"year": 2021, "price": 100, "dividend": 2, "yoy_change": 5}],
            },
        ]
        results = run_collection(container_with_success_agent, tickers_data)
        assert len(results["ONE"]) == 1
        assert results["ONE"][0]["success"] is True


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRunCollectionIntegration:
    """
    Integration: реальный Container + EventGenerationAgent + MockEngine.
    """

    def test_full_run_with_mock_data(self, integration_container, mock_tickers_data):
        results = run_collection(integration_container, mock_tickers_data)

        assert len(results) == len(mock_tickers_data)

        total = sum(len(records) for records in results.values())
        expected_total = sum(len(t["records"]) for t in mock_tickers_data)
        assert total == expected_total

        for ticker, records in results.items():
            for r in records:
                assert r["success"] is True, (
                    f"Integration fail: {ticker}/{r['year']}: {r['error']}"
                )
                assert r["data"] is not None
                assert "reason_short" in r["data"]

    def test_full_run_results_have_duration(self, integration_container, mock_tickers_data):
        results = run_collection(integration_container, mock_tickers_data)
        for ticker, records in results.items():
            for r in records:
                assert r["duration_ms"] is not None
                assert r["duration_ms"] >= 0