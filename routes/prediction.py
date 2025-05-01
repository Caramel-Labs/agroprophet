import os
import joblib
import sqlite3
import numpy as np
from fastapi import APIRouter
from fastapi import HTTPException
from settings import DB_PATH, MODELS_PATH
from sklearn.calibration import LabelEncoder
from payloads.prediction import PricePredictionPayload

# Setup prediction router
router = APIRouter(
    prefix="/api/predict",
    tags=["Prediction"],
)

# --------------------------------
#             ROUTES
# --------------------------------


@router.post("/")
def predict_prices(data: PricePredictionPayload):
    # Insert the new price into the DB
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO price (date, region, crop, price) VALUES (?, ?, ?, ?)",
            (data.date, data.region, data.commodity, data.price),
        )
        conn.commit()

    # Retrieve the latest 4 weeks of price data (including the new one)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT price FROM price
            WHERE region = ? AND crop = ?
              AND date <= ?
            ORDER BY date DESC
            LIMIT 4
            """,
            (data.region, data.commodity, data.date),
        )
        rows = cursor.fetchall()

    if len(rows) < 4:
        raise HTTPException(
            status_code=400,
            detail="Not enough historical data to make a prediction (need at least 4 weeks of price data).",
        )

    # Reverse to get oldest to newest
    last_4_week_prices = [row[0] for row in reversed(rows)]

    # Load appropriate model
    model_path = os.path.join(
        MODELS_PATH, f"{data.region}__{data.type}.joblib".replace(" ", "_")
    )

    if not os.path.exists(model_path):
        raise HTTPException(
            status_code=404, detail="Model not found for given region and type."
        )

    model_data = joblib.load(model_path)
    model = model_data["model"]
    le: LabelEncoder = model_data["label_encoder"]

    # Encode commodity
    try:
        commodity_enc = le.transform([data.commodity])[0]
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown commodity.")

    # Predict
    X_input = np.array([[commodity_enc] + last_4_week_prices])
    y_pred = model.predict(X_input)[0].tolist()

    return {
        "commodity": data.commodity,
        "region": data.region,
        "type": data.type,
        "input_prices": last_4_week_prices,
        "predicted_prices_next_4_weeks": y_pred,
    }
