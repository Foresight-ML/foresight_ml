"""Predict endpoint router."""

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.api.schemas import PredictRequest, PredictResponse
from src.models.explain import get_top_features

router = APIRouter(tags=["Prediction"])


@router.post("/predict", response_model=PredictResponse)
async def make_prediction(request: PredictRequest) -> PredictResponse:
    """Generates a distress probability score for a given company."""
    # WE MOVED IT HERE! This stops the circular import.
    from src.api.main import ml_models

    # Safety check: ensure models loaded correctly on startup
    if "model" not in ml_models or "scaler" not in ml_models:
        raise HTTPException(status_code=503, detail="Models are not loaded and ready.")

    try:
        # 1. Convert the incoming JSON request into a Pandas DataFrame
        input_data = pd.DataFrame(
            [
                {
                    "total_assets": request.total_assets,
                    "total_liabilities": request.total_liabilities,
                    "net_income": request.net_income,
                }
            ]
        )

        # 2. Apply the scaler to normalize the financial numbers
        scaled_data = ml_models["scaler"].transform(input_data)

        # 3. Generate the probability score (0 to 1)
        # predict_proba returns an array like [[prob_class_0, prob_class_1]]
        probability = ml_models["model"].predict(scaled_data)[0]

        # 4. Determine risk level based on the score
        risk_level = "High" if probability >= 0.70 else "Medium" if probability >= 0.40 else "Low"

        # 5. Call your SHAP helper function
        quarter = f"{request.fiscal_year}-{request.fiscal_period}"
        top_features = get_top_features(cik=request.firm_id, quarter=quarter)

        # 6. Format and return the final response
        return PredictResponse(
            distress_probability=float(probability),
            risk_level=risk_level,
            top_features=top_features,
            confidence_interval=[max(0.0, probability - 0.05), min(1.0, probability + 0.05)],
            model_version="v1.0",
            scored_at=datetime.utcnow().isoformat() + "Z",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}") from e
