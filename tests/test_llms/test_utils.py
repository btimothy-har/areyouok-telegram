"""Tests for LLM utilities."""

import dspy

from areyouok_telegram.llms.utils import merge_dspy_usage_data


class TestMergeDspyUsageData:
    """Test the merge_dspy_usage_data function."""

    def test_merge_empty_predictions(self):
        """Test merging empty predictions returns empty dict."""
        result = merge_dspy_usage_data()
        assert result == {}

    def test_merge_predictions_without_usage(self):
        """Test merging predictions without usage data."""
        # Create predictions without usage data
        pred1 = dspy.Prediction(answer="test1")
        pred2 = dspy.Prediction(answer="test2")

        result = merge_dspy_usage_data(pred1, pred2)
        assert result == {}

    def test_merge_single_prediction_with_usage(self):
        """Test merging a single prediction with usage data."""
        pred = dspy.Prediction(answer="test")
        usage_data = {
            "model-1": {
                "completion_tokens": 10,
                "prompt_tokens": 20,
                "total_tokens": 30,
                "completion_tokens_details": {"test": "data"},
                "prompt_tokens_details": {"test": "data"},
            }
        }
        pred.set_lm_usage(usage_data)

        result = merge_dspy_usage_data(pred)
        assert result == usage_data

    def test_merge_multiple_predictions_same_model(self):
        """Test merging multiple predictions using the same model."""
        # Create predictions with usage data
        pred1 = dspy.Prediction(answer="test1")
        pred1.set_lm_usage(
            {
                "model-1": {
                    "completion_tokens": 10,
                    "prompt_tokens": 20,
                    "total_tokens": 30,
                }
            }
        )

        pred2 = dspy.Prediction(answer="test2")
        pred2.set_lm_usage(
            {
                "model-1": {
                    "completion_tokens": 15,
                    "prompt_tokens": 25,
                    "total_tokens": 40,
                }
            }
        )

        result = merge_dspy_usage_data(pred1, pred2)

        assert result["model-1"]["completion_tokens"] == 25  # 10 + 15
        assert result["model-1"]["prompt_tokens"] == 45  # 20 + 25
        assert result["model-1"]["total_tokens"] == 70  # 30 + 40

    def test_merge_multiple_predictions_different_models(self):
        """Test merging predictions from different models."""
        pred1 = dspy.Prediction(answer="test1")
        pred1.set_lm_usage(
            {
                "model-1": {
                    "completion_tokens": 10,
                    "prompt_tokens": 20,
                    "total_tokens": 30,
                }
            }
        )

        pred2 = dspy.Prediction(answer="test2")
        pred2.set_lm_usage(
            {
                "model-2": {
                    "completion_tokens": 15,
                    "prompt_tokens": 25,
                    "total_tokens": 40,
                }
            }
        )

        result = merge_dspy_usage_data(pred1, pred2)

        assert "model-1" in result
        assert "model-2" in result
        assert result["model-1"]["total_tokens"] == 30
        assert result["model-2"]["total_tokens"] == 40

    def test_merge_preserves_latest_details(self):
        """Test that merge preserves the latest token details."""
        pred1 = dspy.Prediction(answer="test1")
        pred1.set_lm_usage(
            {
                "model-1": {
                    "completion_tokens": 10,
                    "prompt_tokens": 20,
                    "total_tokens": 30,
                    "completion_tokens_details": {"old": "data"},
                }
            }
        )

        pred2 = dspy.Prediction(answer="test2")
        pred2.set_lm_usage(
            {
                "model-1": {
                    "completion_tokens": 15,
                    "prompt_tokens": 25,
                    "total_tokens": 40,
                    "completion_tokens_details": {"new": "data"},
                }
            }
        )

        result = merge_dspy_usage_data(pred1, pred2)

        # Should have the newer details
        assert result["model-1"]["completion_tokens_details"] == {"new": "data"}

    def test_merge_mixed_predictions(self):
        """Test merging a mix of predictions with and without usage."""
        pred1 = dspy.Prediction(answer="test1")
        pred1.set_lm_usage(
            {
                "model-1": {
                    "completion_tokens": 10,
                    "prompt_tokens": 20,
                    "total_tokens": 30,
                }
            }
        )

        pred2 = dspy.Prediction(answer="test2")  # No usage

        pred3 = dspy.Prediction(answer="test3")
        pred3.set_lm_usage(
            {
                "model-1": {
                    "completion_tokens": 5,
                    "prompt_tokens": 10,
                    "total_tokens": 15,
                }
            }
        )

        result = merge_dspy_usage_data(pred1, pred2, pred3)

        assert result["model-1"]["completion_tokens"] == 15  # 10 + 5
        assert result["model-1"]["prompt_tokens"] == 30  # 20 + 10
        assert result["model-1"]["total_tokens"] == 45  # 30 + 15
