from pathlib import Path

import joblib
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

MODEL_PATH = (
    PROJECT_ROOT
    / "ml"
    / "models"
    / "xgb_v4.joblib"
)


class MLPredictionService:

    def __init__(self, model_path: Path = MODEL_PATH):
        self.model_path = model_path
        self.model = joblib.load(model_path)

    def predict_win_probability(
        self,
        features: dict
    ) -> float:

        feature_df = pd.DataFrame([features])

        probability = self.model.predict_proba(
            feature_df
        )[0][1]

        return float(probability)