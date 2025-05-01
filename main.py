import os
import joblib
import sqlite3
import numpy as np
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from sklearn.calibration import LabelEncoder
from fastapi.middleware.cors import CORSMiddleware

# Instantiate FastAPI application
app = FastAPI(
    title="AgroProphet",
    description="AgroProphet - Cold Storage Solution.",
)

# SQLite DB setup
db_path = "agroprophet.db"


def init_db():
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS price (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                region TEXT NOT NULL,
                crop TEXT NOT NULL,
                price REAL NOT NULL
            )
        """
        )
        conn.commit()


# Call this once at startup
init_db()

# Define directory with saved models
model_dir = "models"


class CommodityInput(BaseModel):
    region: str
    type: str
    commodity: str
    last_4_week_prices: list[float]  # [lag_1, lag_2, lag_3, lag_4]


# Define allowed origins for CORS
origins = [
    "*",
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:4000",
]

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root route (to test service health)
@app.get("/", tags=["Internals"])
async def root():
    return {
        "message": "AgroProphet is up and running! Navigate to /docs to view the SwaggerUI.",
    }


@app.post("/predict")
def predict_prices(data: CommodityInput):
    model_path = os.path.join(
        model_dir, f"{data.region}__{data.type}.joblib".replace(" ", "_")
    )

    if not os.path.exists(model_path):
        raise HTTPException(
            status_code=404,
            detail="Model not found for given region and type.",
        )

    model_data = joblib.load(model_path)
    model = model_data["model"]
    le: LabelEncoder = model_data["label_encoder"]

    try:
        commodity_enc = le.transform([data.commodity])[0]

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Unknown commodity.",
        )

    X_input = np.array([[commodity_enc] + data.last_4_week_prices])
    y_pred = model.predict(X_input)[0].tolist()

    return {
        "commodity": data.commodity,
        "region": data.region,
        "type": data.type,
        "predicted_prices_next_4_weeks": y_pred,
    }


@app.post("/api/data/prices", tags=["Data Collection"])
def store_price_data(payload: dict):
    # Validate required fields
    try:
        date = payload["date"]
        region = payload["region"]
        crop = payload["crop"]
        price = payload["priceData"]["price"]
    except KeyError:
        raise HTTPException(status_code=400, detail="Missing required fields.")

    # Store in SQLite DB
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO price (date, region, crop, price) VALUES (?, ?, ?, ?)",
            (date, region, crop, price),
        )
        conn.commit()

    return {"message": "Price data saved successfully."}
