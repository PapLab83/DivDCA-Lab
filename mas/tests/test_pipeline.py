# mas/tests/test_pipeline.py
"""
Тесты для pipeline.process_ticker.

Unit-тесты: подставные агенты (AlwaysSuccess, AlwaysFail, PartialFail).
Integration-тесты: реальный EventGenerationAgent + MockEngine.
"""

from mas.price_drivers_collection.pipeline import process_ticker


# ═══════════════════════════════════════════════════════════════════
# UNIT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProcessTickerSuccess:
    """Сценарии с успешным агентом."""

    def test_returns_list(self, success_agent, single_ticker_data):
        results = process_ticker(
            agent=success_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        assert isinstance(results, list)

    def test_result_count_matches_records(self, success_agent, single_ticker_data):
        results = process_ticker(
            agent=success_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        assert len(results) == len(single_ticker_data["records"])

    def test_all_results_successful(self, success_agent, single_ticker_data):
        results = process_ticker(
            agent=success_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        for r in results:
            assert r["success"] is True
            assert r["error"] is None

    def test_result_contains_required_fields(self, success_agent, single_ticker_data):
        results = process_ticker(
            agent=success_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        required_keys = {"ticker", "year", "success", "data", "error", "duration_ms", "prompt_version"}
        for r in results:
            missing = required_keys - set(r.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_ticker_and_year_propagated(self, success_agent, single_ticker_data):
        results = process_ticker(
            agent=success_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        for r, record in zip(results, single_ticker_data["records"]):
            assert r["ticker"] == single_ticker_data["ticker"]
            assert r["year"] == record["year"]

    def test_data_contains_agent_output(self, success_agent, single_ticker_data):
        results = process_ticker(
            agent=success_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        for r in results:
            assert "reason_short" in r["data"]
            assert "confidence" in r["data"]

    def test_duration_is_non_negative(self, success_agent, single_ticker_data):
        results = process_ticker(
            agent=success_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        for r in results:
            assert r["duration_ms"] is not None
            assert r["duration_ms"] >= 0


class TestProcessTickerFailure:
    """Сценарии с падающим агентом."""

    def test_all_results_failed(self, fail_agent, single_ticker_data):
        results = process_ticker(
            agent=fail_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        for r in results:
            assert r["success"] is False
            assert r["error"] is not None
            assert r["data"] is None

    def test_error_contains_exception_info(self, fail_agent, single_ticker_data):
        results = process_ticker(
            agent=fail_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        for r in results:
            assert "RuntimeError" in r["error"] or "Simulated" in r["error"]

    def test_failure_does_not_stop_processing(self, fail_agent, single_ticker_data):
        """Pipeline должен обработать ВСЕ записи, даже если каждая падает."""
        results = process_ticker(
            agent=fail_agent,
            ticker=single_ticker_data["ticker"],
            records=single_ticker_data["records"],
        )
        assert len(results) == len(single_ticker_data["records"])


class TestProcessTickerPartialFailure:
    """Сценарии со смешанными результатами."""

    def test_mixed_results(self, partial_fail_agent):
        records = [
            {"year": 2019, "price": 100, "dividend": 2, "yoy_change": 5},  # odd → success
            {"year": 2020, "price": 110, "dividend": 2, "yoy_change": 5},  # even → fail
            {"year": 2021, "price": 120, "dividend": 2, "yoy_change": 5},  # odd → success
            {"year": 2022, "price": 130, "dividend": 2, "yoy_change": 5},  # even → fail
        ]
        results = process_ticker(
            agent=partial_fail_agent,
            ticker="MIX",
            records=records,
        )
        assert len(results) == 4
        assert results[0]["success"] is True   # 2019
        assert results[1]["success"] is False  # 2020
        assert results[2]["success"] is True   # 2021
        assert results[3]["success"] is False  # 2022

    def test_successful_results_have_data(self, partial_fail_agent):
        records = [
            {"year": 2019, "price": 100, "dividend": 2, "yoy_change": 5},
            {"year": 2020, "price": 110, "dividend": 2, "yoy_change": 5},
        ]
        results = process_ticker(
            agent=partial_fail_agent,
            ticker="MIX",
            records=records,
        )
        assert results[0]["data"] is not None
        assert results[1]["data"] is None


class TestProcessTickerEdgeCases:
    """Граничные случаи."""

    def test_empty_records_returns_empty(self, success_agent):
        results = process_ticker(agent=success_agent, ticker="EMPTY", records=[])
        assert results == []

    def test_single_record(self, success_agent, single_record):
        results = process_ticker(
            agent=success_agent,
            ticker="SINGLE",
            records=[single_record],
        )
        assert len(results) == 1
        assert results[0]["success"] is True

    def test_negative_yoy_change(self, success_agent):
        records = [{"year": 2022, "price": 50, "dividend": 1, "yoy_change": -46.6}]
        results = process_ticker(agent=success_agent, ticker="NEG", records=records)
        assert len(results) == 1
        assert results[0]["success"] is True

    def test_zero_dividend(self, success_agent):
        records = [{"year": 2022, "price": 100, "dividend": 0.0, "yoy_change": -100.0}]
        results = process_ticker(agent=success_agent, ticker="ZERO", records=records)
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProcessTickerIntegration:
    """
    Integration: реальный EventGenerationAgent + MockEngine + PromptManager.
    Проверяет, что вся цепочка Container → Factory → Agent → LLM → parse работает.
    """

    def test_full_pipeline_single_record(self, integration_agent):
        records = [{"year": 2021, "price": 150.0, "dividend": 3.0, "yoy_change": 10.0}]
        results = process_ticker(agent=integration_agent, ticker="INTG", records=records)

        assert len(results) == 1
        r = results[0]
        assert r["success"] is True
        assert r["ticker"] == "INTG"
        assert r["year"] == 2021
        assert "reason_short" in r["data"]
        assert "reason_long" in r["data"]
        assert "confidence" in r["data"]

    def test_full_pipeline_multiple_records(self, integration_agent):
        records = [
            {"year": 2019, "price": 73.41, "dividend": 0.75, "yoy_change": 5.5},
            {"year": 2020, "price": 131.96, "dividend": 0.80, "yoy_change": 6.7},
            {"year": 2021, "price": 177.57, "dividend": 0.85, "yoy_change": 6.3},
        ]
        results = process_ticker(agent=integration_agent, ticker="AAPL", records=records)

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert all(r["duration_ms"] >= 0 for r in results)

    def test_full_pipeline_with_mock_tickers(self, integration_agent, mock_tickers_data):
        """Прогоняет ВСЕ mock-данные через реальный pipeline."""
        for ticker_data in mock_tickers_data:
            results = process_ticker(
                agent=integration_agent,
                ticker=ticker_data["ticker"],
                records=ticker_data["records"],
            )
            assert len(results) == len(ticker_data["records"])
            for r in results:
                assert r["success"] is True, (
                    f"Failed: {r['ticker']}/{r['year']}: {r['error']}"
                )

    def test_prompt_version_is_set(self, integration_agent):
        records = [{"year": 2021, "price": 100, "dividend": 2, "yoy_change": 5}]
        results = process_ticker(agent=integration_agent, ticker="VER", records=records)
        assert results[0]["prompt_version"] is not None