"""
Demand forecasting service using moving average and linear trend models.
Calculates WAPE and forecast accuracy with explicit zero-demand safeguards.
WAPE = (Sum(|Actual - Predicted|) / Sum(Actual)) * 100.
Accuracy = max(0.0, 100.0 - WAPE) if WAPE is defined.
"""

import logging
from datetime import timedelta, date
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Product
from orders.models import Order, OrderItem
from inventory.models import ForecastModel, ForecastPrediction

logger = logging.getLogger(__name__)


class ForecastService:
    """Trains forecasting models and produces chronological daily demand predictions."""

    @classmethod
    def get_daily_sales_series(
        cls,
        product: Product,
        days: int = 90,
    ) -> List[Tuple[date, float]]:
        """
        Extract daily chronological sales volume for product over the last `days`.
        Fills missing dates with 0.0 units.
        """
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        qualifying_statuses = [
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ]

        # Aggregate daily sales
        items = (
            OrderItem.objects.filter(
                product=product,
                order__status__in=qualifying_statuses,
                order__created_at__date__gte=start_date,
                order__created_at__date__lt=end_date,
            )
            .values('order__created_at__date')
            .annotate(daily_units=Sum('quantity'))
        )
        sales_by_date = {entry['order__created_at__date']: float(entry['daily_units']) for entry in items}

        series = []
        curr = start_date
        while curr < end_date:
            series.append((curr, sales_by_date.get(curr, 0.0)))
            curr += timedelta(days=1)

        return series

    @classmethod
    def calculate_wape(
        cls,
        actuals: List[float],
        predictions: List[float],
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Compute Weighted Absolute Percentage Error (WAPE) and Forecast Accuracy.
        Returns: (wape, accuracy) or (None, None) if actual demand sum is 0.
        """
        if not actuals or not predictions or len(actuals) != len(predictions):
            return None, None

        act_arr = np.array(actuals, dtype=float)
        pred_arr = np.array(predictions, dtype=float)

        total_actual = np.sum(act_arr)
        total_abs_error = np.sum(np.abs(act_arr - pred_arr))

        if total_actual == 0:
            if total_abs_error == 0:
                return 0.0, 100.0
            return None, None  # Cannot divide by zero total actual demand

        wape = float((total_abs_error / total_actual) * 100.0)
        accuracy = max(0.0, float(100.0 - wape))
        return round(wape, 2), round(accuracy, 2)

    @classmethod
    def train_and_forecast_product(
        cls,
        product: Product,
        history_days: int = 60,
        forecast_horizon_days: int = 14,
        window_size: int = 7,
    ) -> ForecastModel:
        """
        Train a moving-average forecast with chronological train/test holdout validation.
        Generates ForecastModel and future ForecastPrediction records.
        """
        series = cls.get_daily_sales_series(product, days=history_days)
        values = [val for _, val in series]
        dates = [d for d, _ in series]

        total_points = len(values)
        if total_points >= 14:
            # Chronological split: 80% train, 20% validation
            split_idx = int(total_points * 0.8)
            train_vals = values[:split_idx]
            val_vals = values[split_idx:]

            # Moving average prediction on validation window
            val_preds = []
            history_window = list(train_vals[-window_size:]) if len(train_vals) >= window_size else list(train_vals)
            for _ in range(len(val_vals)):
                pred = float(np.mean(history_window)) if history_window else 0.0
                val_preds.append(max(0.0, pred))
                history_window.pop(0)
                history_window.append(pred)

            wape, accuracy = cls.calculate_wape(val_vals, val_preds)
            val_sample_size = len(val_vals)
        else:
            wape, accuracy = None, None
            val_sample_size = 0

        # Model parameter estimation for forward prediction
        recent_window = values[-window_size:] if len(values) >= window_size else values
        baseline_rate = float(np.mean(recent_window)) if recent_window else 0.0

        # Estimate standard deviation for prediction intervals
        std_dev = float(np.std(recent_window)) if len(recent_window) > 1 else max(0.5, baseline_rate * 0.2)

        # Deactivate older models for this product
        ForecastModel.objects.filter(product=product, is_active=True).update(is_active=False)

        model = ForecastModel.objects.create(
            model_type='MOVING_AVERAGE',
            version='v1.0',
            product=product,
            training_cutoff=timezone.now(),
            forecast_horizon_days=forecast_horizon_days,
            metrics={
                'wape': wape,
                'forecast_accuracy': accuracy,
                'validation_sample_size': val_sample_size,
                'history_days_used': len(values),
                'evaluation_period': f"Last {val_sample_size} days holdout",
            },
            parameters={
                'window_size': window_size,
                'baseline_daily_rate': round(baseline_rate, 2),
                'daily_std_dev': round(std_dev, 2),
            },
            is_active=True,
        )

        # Generate future daily predictions
        today = timezone.now().date()
        ForecastPrediction.objects.filter(product=product, prediction_date__gte=today).delete()

        predictions = []
        for i in range(1, forecast_horizon_days + 1):
            pred_date = today + timedelta(days=i)
            pred_val = round(max(0.0, baseline_rate), 2)
            lower = round(max(0.0, pred_val - 1.96 * std_dev), 2)
            upper = round(pred_val + 1.96 * std_dev, 2)

            predictions.append(
                ForecastPrediction(
                    forecast_model=model,
                    product=product,
                    prediction_date=pred_date,
                    predicted_demand=pred_val,
                    lower_bound=lower,
                    upper_bound=upper,
                )
            )

        ForecastPrediction.objects.bulk_create(predictions)
        logger.info(f"Forecast model v1.0 trained for {product.sku}: Accuracy={accuracy}%, WAPE={wape}%")
        return model

    @classmethod
    def train_all_forecasts(cls) -> int:
        """Train models and generate predictions for all active products."""
        count = 0
        for product in Product.objects.filter(status=Product.Status.ACTIVE):
            cls.train_and_forecast_product(product)
            count += 1
        return count
