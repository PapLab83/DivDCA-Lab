"""
Тесты валидации структуры mock-данных.
Гарантируют, что тестовые данные корректны до запуска pipeline.
"""
from mas.price_drivers_collection.mock_data import MOCK_TICKERS


class TestMockDataStructure:
    """Валидация формата mock-данных."""

    def test_mock_tickers_not_empty(self):
        assert len(MOCK_TICKERS) > 0

    def test_each_ticker_has_required_fields(self):
        for ticker_data in MOCK_TICKERS:
            assert "ticker" in ticker_data, f"Missing 'ticker' key"
            assert "records" in ticker_data, f"Missing 'records' for {ticker_data.get('ticker')}"
            assert isinstance(ticker_data["ticker"], str)
            assert isinstance(ticker_data["records"], list)

    def test_each_record_has_required_fields(self):
        required = {"year", "price", "dividend", "yoy_change"}
        for ticker_data in MOCK_TICKERS:
            ticker = ticker_data["ticker"]
            for i, record in enumerate(ticker_data["records"]):
                missing = required - set(record.keys())
                assert not missing, (
                    f"{ticker} record[{i}]: missing fields {missing}"
                )

    def test_numeric_fields_are_valid(self):
        for ticker_data in MOCK_TICKERS:
            ticker = ticker_data["ticker"]
            for record in ticker_data["records"]:
                assert isinstance(record["year"], int), f"{ticker}: year not int"
                assert isinstance(record["price"], (int, float)), f"{ticker}: price not numeric"
                assert isinstance(record["dividend"], (int, float)), f"{ticker}: dividend not numeric"
                assert record["price"] > 0, f"{ticker}/{record['year']}: price <= 0"
                assert record["dividend"] >= 0, f"{ticker}/{record['year']}: dividend < 0"

    def test_years_are_reasonable(self):
        for ticker_data in MOCK_TICKERS:
            for record in ticker_data["records"]:
                assert 1900 < record["year"] < 2100

    def test_unique_tickers(self):
        tickers = [t["ticker"] for t in MOCK_TICKERS]
        assert len(tickers) == len(set(tickers)), "Duplicate tickers found"