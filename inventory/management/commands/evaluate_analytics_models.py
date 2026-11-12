"""
Command to evaluate demand forecast and recommendation accuracy on chronological holdout sets.
"""

from django.core.management.base import BaseCommand
from inventory.services import RecommendationService, ForecastService


class Command(BaseCommand):
    help = 'Evaluate analytics models (Recommendation Precision@K and Forecast WAPE/Accuracy) using chronological holdout data.'

    def add_arguments(self, parser):
        parser.add_argument('--k', type=int, default=5, help='K-value for recommendation evaluation (default: 5)')
        parser.add_argument('--holdout-days', type=int, default=30, help='Chronological holdout window in days (default: 30)')

    def handle(self, *args, **options):
        k = options['k']
        holdout_days = options['holdout_days']

        self.stdout.write(self.style.NOTICE(f'Evaluating recommendations (P@{k}, holdout: {holdout_days}d)...'))
        rec_eval = RecommendationService.evaluate_recommendations(k=k, holdout_days=holdout_days)

        self.stdout.write(self.style.SUCCESS(
            f"Recommendation Evaluation: Precision@{k} = {rec_eval.precision_at_k:.3f}, "
            f"Catalog Coverage = {rec_eval.coverage_percentage}%, "
            f"Sample Size = {rec_eval.sample_size} customers."
        ))
