"""
Locust Performance and Load Testing Suite for ShopSense Analytics APIs (Module 10).
Simulates realistic concurrent user traffic across all 6 analytical API categories:
1. Vendor Analytics (`/api/v1/analytics/vendor/summary`)
2. Demand Forecasting (`/api/v1/analytics/forecast/{sku}`)
3. Customer Intelligence (`/api/v1/analytics/customers/segments`)
4. Product Recommendations (`/api/v1/analytics/recommendations/popular`)
5. Revenue Analytics (`/api/v1/analytics/revenue/daily`, `/api/v1/analytics/revenue/monthly`)
6. Marketplace Benchmarking (`/api/v1/analytics/benchmarking/marketplace`)

Validation Target: P95 response time <= 300ms.
"""

from locust import HttpUser, between, task


class ShopSenseAnalyticsUser(HttpUser):
    """Simulates active merchants and platform administrators querying analytical APIs."""

    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Configure authentication headers for the simulated load session."""
        self.headers = {
            "Authorization": "Bearer admin@shopsense.com",
            "X-User-Email": "admin@shopsense.com",
            "Accept": "application/json",
        }

    @task(3)
    def test_daily_revenue(self):
        """Query 30-day daily sales timeseries."""
        self.client.get(
            "/api/v1/analytics/revenue/daily?days=30",
            headers=self.headers,
            name="GET /api/v1/analytics/revenue/daily",
        )

    @task(3)
    def test_monthly_revenue(self):
        """Query monthly revenue aggregates."""
        self.client.get(
            "/api/v1/analytics/revenue/monthly?months=6",
            headers=self.headers,
            name="GET /api/v1/analytics/revenue/monthly",
        )

    @task(2)
    def test_vendor_summary(self):
        """Query multi-tenant vendor analytics."""
        self.client.get(
            "/api/v1/analytics/vendor/summary",
            headers=self.headers,
            name="GET /api/v1/analytics/vendor/summary",
        )

    @task(2)
    def test_customer_segments(self):
        """Query RFM customer segment distribution."""
        self.client.get(
            "/api/v1/analytics/customers/segments",
            headers=self.headers,
            name="GET /api/v1/analytics/customers/segments",
        )

    @task(2)
    def test_popular_recommendations(self):
        """Query top recommended product candidates."""
        self.client.get(
            "/api/v1/analytics/recommendations/popular?limit=5",
            headers=self.headers,
            name="GET /api/v1/analytics/recommendations/popular",
        )

    @task(2)
    def test_marketplace_benchmarks(self):
        """Query marketplace benchmarking metrics."""
        self.client.get(
            "/api/v1/analytics/benchmarking/marketplace",
            headers=self.headers,
            name="GET /api/v1/analytics/benchmarking/marketplace",
        )

    @task(1)
    def test_demand_forecast(self):
        """Query Holt-Winters predictive demand forecast for a SKU."""
        self.client.get(
            "/api/v1/analytics/forecast/SW-PRO-01?horizon_days=30",
            headers=self.headers,
            name="GET /api/v1/analytics/forecast/{sku}",
        )
