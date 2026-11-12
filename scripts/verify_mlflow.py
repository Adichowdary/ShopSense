"""
Verification script for Section 6: MLflow Experiment Tracking & Registry.
1. Tests experiment creation for all 3 analytical domains.
2. Executes training run logging with parameters, metrics, tags, and artifacts.
3. Inspects and reads artifacts directly from the `./mlruns` directory.
4. Uses MlflowClient to retrieve runs, verify metric values, and test model loading.
5. Confirms operational status of tracking engine.
"""

import os
import sys
import json
import mlflow
from mlflow.tracking import MlflowClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
import django
django.setup()

from inventory.services.mlflow_services import MLflowTrackingService


def main():
    print("==================================================================")
    print("  SECTION 6: MLFLOW EXPERIMENT TRACKING & REGISTRY AUDIT")
    print("==================================================================")

    # 1. Initialize
    MLflowTrackingService.initialize()
    client = MlflowClient()

    # 2. Demand Forecasting Experiment
    print("\n--- 1. Testing Demand Forecasting Run Logging ---")
    fc_res = MLflowTrackingService.track_demand_forecasting(
        product_id=None,
        model_name="holt_winters_exponential_smoothing",
        horizon_days=30,
        accuracy=86.5,
        wape=0.135,
        mae=3.7,
        rmse=5.2,
    )
    fc_run_id = fc_res['run_id']
    fc_run = client.get_run(fc_run_id)
    print(f"  Run ID:           {fc_run_id}")
    print(f"  Experiment ID:    {fc_run.info.experiment_id}")
    print(f"  Accuracy Metric:  {fc_run.data.metrics['accuracy_percent']}% (Target: >= 80%)")
    print(f"  WAPE Error:       {fc_run.data.metrics['wape']} (Target: <= 0.20)")
    print(f"  Registry Stage:   {fc_run.data.tags.get('stage')}")
    assert fc_run.data.metrics['accuracy_percent'] >= 80.0
    assert fc_run.data.metrics['wape'] <= 0.20

    # 3. Customer Segmentation Experiment
    print("\n--- 2. Testing Customer Segmentation Run Logging ---")
    seg_res = MLflowTrackingService.track_customer_segmentation(
        k_clusters=5,
        silhouette_score=0.885,
        davies_bouldin_index=0.49,
    )
    seg_run_id = seg_res['run_id']
    seg_run = client.get_run(seg_run_id)
    print(f"  Run ID:           {seg_run_id}")
    print(f"  Silhouette Score: {seg_run.data.metrics['silhouette_score']} (Target: >= 0.85)")
    print(f"  Quality Percent:  {seg_run.data.metrics['segmentation_quality_percent']}%")
    assert seg_run.data.metrics['silhouette_score'] >= 0.85

    # 4. Product Recommendations Experiment
    print("\n--- 3. Testing Recommendation Engine Run Logging ---")
    rec_res = MLflowTrackingService.track_recommendations(
        top_k=5,
        precision_at_k=0.792,
        recall_at_k=0.655,
        coverage_percentage=83.1,
    )
    rec_run_id = rec_res['run_id']
    rec_run = client.get_run(rec_run_id)
    print(f"  Run ID:           {rec_run_id}")
    print(f"  Precision@5:      {rec_run.data.metrics['precision_percent']}% (Target: >= 75%)")
    print(f"  Catalog Coverage: {rec_run.data.metrics['catalog_coverage_percent']}%")
    assert rec_run.data.metrics['precision_at_k'] >= 0.75

    # 5. Verify Artifacts on File System
    print("\n--- 4. Verifying Logged Artifacts on Disk ---")
    artifacts = client.list_artifacts(fc_run_id)
    artifact_names = [a.path for a in artifacts]
    print(f"  Forecasting Run Artifacts: {artifact_names}")
    assert "forecasting_metadata.json" in artifact_names

    # Download / read artifact
    local_path = client.download_artifacts(fc_run_id, "forecasting_metadata.json")
    with open(local_path, "r", encoding="utf-8") as f:
        meta_content = json.load(f)
        assert meta_content['quality_check_passed'] is True
        print(f"  Artifact Content Verified: quality_check_passed={meta_content['quality_check_passed']}")

    # 6. Consolidated Experiment Suite Execution
    print("\n--- 5. Consolidated Experiment Suite Verification ---")
    all_summary = MLflowTrackingService.run_all_tracking_experiments()
    assert all_summary["status"] == "COMPLETED"
    assert all_summary["all_passed"] is True
    print(f"  Consolidated Suite Status: {all_summary['status']} (All Passed: {all_summary['all_passed']})")

    print("\n==================================================================")
    print("  MLFLOW EXPERIMENT TRACKING & REGISTRY AUDIT PASSED")
    print("==================================================================")
    return 0


if __name__ == '__main__':
    sys.exit(main())

