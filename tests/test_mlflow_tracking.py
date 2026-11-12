"""
Tests for MLflow Model Tracking and Registry (Module 8).
Validates:
1. Demand Forecasting tracking: accuracy >= 80%, WAPE <= 0.20, parameters, tags, artifact logging.
2. Customer Segmentation tracking: silhouette score >= 0.85, parameters, tags, artifact logging.
3. Recommendation Engine tracking: precision@5 >= 75%, parameters, tags, artifact logging.
4. Consolidated tracking suite: all 3 models pass quantitative targets.
"""

import os
import pytest
from django.utils import timezone

from inventory.services.mlflow_services import MLflowTrackingService


@pytest.mark.django_db
class TestMLflowModelTracking:
    """Validate MLflow experiment runs and quantitative criteria."""

    def test_tracking_initialization(self):
        MLflowTrackingService.initialize()
        assert os.path.exists("./mlruns")

    def test_demand_forecasting_tracking(self):
        result = MLflowTrackingService.track_demand_forecasting(
            product_id=None,
            model_name="holt_winters_exponential_smoothing",
            horizon_days=30,
            accuracy=86.2,
            wape=0.138,
            mae=3.8,
            rmse=5.4,
        )
        assert result["quality_check_passed"] is True
        assert result["metrics"]["accuracy_percent"] >= 80.0
        assert result["metrics"]["wape"] <= 0.20
        assert "run_id" in result
        assert result["parameters"]["horizon_days"] == 30

    def test_customer_segmentation_tracking(self):
        result = MLflowTrackingService.track_customer_segmentation(
            k_clusters=5,
            silhouette_score=0.88,
            davies_bouldin_index=0.48,
        )
        assert result["quality_check_passed"] is True
        assert result["metrics"]["silhouette_score"] >= 0.85
        assert result["metrics"]["segmentation_quality_percent"] >= 85.0
        assert "run_id" in result

    def test_recommendation_tracking(self):
        result = MLflowTrackingService.track_recommendations(
            top_k=5,
            precision_at_k=0.785,
            recall_at_k=0.642,
            coverage_percentage=82.4,
        )
        assert result["quality_check_passed"] is True
        assert result["metrics"]["precision_at_k"] >= 0.75
        assert result["metrics"]["precision_percent"] >= 75.0
        assert "run_id" in result

    def test_run_all_tracking_experiments(self):
        summary = MLflowTrackingService.run_all_tracking_experiments()
        assert summary["status"] == "COMPLETED"
        assert summary["all_passed"] is True
        assert summary["forecasting"]["quality_check_passed"] is True
        assert summary["segmentation"]["quality_check_passed"] is True
        assert summary["recommendations"]["quality_check_passed"] is True

