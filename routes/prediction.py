import os
import joblib
import sqlite3
import numpy as np
from fastapi import APIRouter
from fastapi import HTTPException
from datetime import datetime, timedelta
from sklearn.calibration import LabelEncoder
from payloads.prediction import PredictionPayload
from settings import DB_PATH, MODELS_PATH, FRUITS, VEGETABLES

# Setup prediction router
router = APIRouter(
    prefix="/predict",
    tags=["Prediction"],
)

# --------------------------------
#             ROUTES
# --------------------------------


@router.post("/")
def predict_prices(data: PredictionPayload):
    # 1. Infer crop type
    crop_name = data.crop.strip()
    if crop_name in FRUITS:
        crop_type = "Fruit"
    elif crop_name in VEGETABLES:
        crop_type = "Vegetable"
    else:
        raise HTTPException(
            status_code=400,
            detail="Unknown crop; not categorized as Fruit or Vegetable.",
        )

    # 2. Retrieve last 4 prices
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, price FROM price
            WHERE region = ? AND crop = ?
            ORDER BY date DESC
            LIMIT 4
            """,
            (data.region, crop_name),
        )
        rows = cursor.fetchall()

    if len(rows) < 4:
        raise HTTPException(
            status_code=400,
            detail="Not enough historical data to make a prediction (need at least 4 weeks of price data).",
        )

    # 3. Sort and prepare lag values
    sorted_rows = sorted(rows, key=lambda x: x[0])
    last_4_week_prices = [row[1] for row in sorted_rows]
    latest_date = datetime.strptime(sorted_rows[-1][0], "%Y-%m-%d")

    # 4. Load model
    model_path = os.path.join(
        MODELS_PATH, f"{data.region}__{crop_type}.joblib".replace(" ", "_")
    )

    if not os.path.exists(model_path):
        raise HTTPException(
            status_code=404,
            detail=f"Model not found for region '{data.region}' and crop type '{crop_type}'.",
        )

    model_data = joblib.load(model_path)
    model = model_data["model"]
    encoder: LabelEncoder = model_data["label_encoder"]

    # 5. Encode crop name
    try:
        crop_enc = encoder.transform([crop_name])[0]
    except ValueError:
        raise HTTPException(status_code=400, detail="Crop not recognized by the model.")

    # 6. Predict
    X_input = np.array([[crop_enc] + last_4_week_prices])
    y_pred = model.predict(X_input)[0].tolist()

    # 7. Build prediction output with future dates
    prediction_output = [
        {
            "prediction_index": i,
            "date": (latest_date + timedelta(weeks=i + 1)).strftime("%Y-%m-%d"),
            "price": round(price, 2),
        }
        for i, price in enumerate(y_pred)
    ]

    return {
        "crop": crop_name,
        "region": data.region,
        "predictions": prediction_output,
    }
