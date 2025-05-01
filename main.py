import os
import joblib
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
