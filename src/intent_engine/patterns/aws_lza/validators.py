"""AWS LZA pattern validators."""

from __future__ import annotations

from intent_engine.core.validator import Violation

from .models import AwsLzaIntent
from .semantic import build_aws_lza_semantic_model


def validate_aws_lza_intent(intent: AwsLzaIntent) -> list[Violation]:
    model = build_aws_lza_semantic_model(intent)
    return [
        Violation(
            code=constraint.violation_code,
            message=constraint.violation_message,
        )
        for constraint in model.failed_constraints()
    ]
