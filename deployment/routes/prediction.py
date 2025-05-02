# routes/prediction.py

import os
import joblib
import sqlite3
import numpy as np
from fastapi import APIRouter
from fastapi import HTTPException
from datetime import datetime, timedelta
from sklearn.calibration import LabelEncoder # Assuming LabelEncoder is used
from payloads.prediction import PredictionPayload # Assuming this Pydantic model exists
from settings import DB_PATH, MODELS_PATH, FRUITS, VEGETABLES # Import necessary settings

# Setup prediction router
router = APIRouter(
    prefix="/predict",
    tags=["Prediction"],
)

# --------------------------------
#             ROUTES
# --------------------------------


@router.post("")
def predict_prices(data: PredictionPayload):
    """
    Generates price predictions for a given crop and region based on historical data.
    """
    # 1. Infer crop type (needed to load the correct model)
    crop_name = data.crop.strip()
    crop_type = None
    if crop_name in FRUITS:
        crop_type = "Fruit"
    elif crop_name in VEGETABLES:
        crop_type = "Vegetable"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown crop '{crop_name}'; not categorized as Fruit or Vegetable. Please add it to settings.py.",
        )

    # 2. Retrieve last 4 *actual* prices for the specific region and crop
    # Ensure you are only getting actual data (actual = 1)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, price FROM price
            WHERE region = ? AND crop = ? AND actual = 1 -- Crucial: only fetch actual data
            ORDER BY date DESC
            LIMIT 4
            """,
            (data.region, crop_name),
        )
        rows = cursor.fetchall()

    # 3. Check if enough historical data is available
    if len(rows) < 4:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough historical data to make a prediction for {crop_name} in {data.region} (need at least 4 weeks of *actual* price data). Found {len(rows)}.",
        )

    # 4. Sort data by date and prepare lag values
    # The data is fetched DESC, so sort ASC for chronological order
    sorted_rows = sorted(rows, key=lambda x: x[0])
    last_4_week_prices = [row[1] for row in sorted_rows]
    latest_date_str = sorted_rows[-1][0]
    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")

    print(f"📈 Using last 4 actual prices for {crop_name} in {data.region} ending {latest_date_str}: {last_4_week_prices}")


    # 5. Load the specific model for the region and crop type
    # Model names are expected in the format Region__CropType.joblib
    model_filename = f"{data.region}__{crop_type}.joblib".replace(" ", "_")
    model_path = os.path.join(MODELS_PATH, model_filename)

    if not os.path.exists(model_path):
        raise HTTPException(
            status_code=404,
            detail=f"Model file '{model_filename}' not found for region '{data.region}' and crop type '{crop_type}'.",
        )

    try:
        model_data = joblib.load(model_path)
        model = model_data["model"]
        # Assuming your saved model data includes the LabelEncoder used during training
        encoder: LabelEncoder = model_data["label_encoder"]
        print(f"✅ Successfully loaded model: {model_filename}")
    except Exception as e:
         raise HTTPException(
            status_code=500,
            detail=f"Error loading or accessing model components from {model_filename}: {e}",
        )


    # 6. Encode the crop name using the model's encoder
    try:
        crop_enc = encoder.transform([crop_name])[0]
        print(f"Crop '{crop_name}' encoded to {crop_enc}")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Crop '{crop_name}' not recognized by the loaded model's encoder. It might not have been included in the training data for this model.")
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error during crop encoding: {e}")


    # 7. Prepare input for the model and make predictions
    # The input features are the encoded crop followed by the 4 lag prices
    X_input = np.array([[crop_enc] + last_4_week_prices])
    try:
        # Model is expected to predict a list/array of future prices
        y_pred = model.predict(X_input)[0].tolist() # Assuming predict returns [prediction1, prediction2, ...]
        print(f"🔮 Model predicted raw prices: {y_pred}")
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error during model prediction: {e}")


    # 8. Build prediction output with future dates and prepare database entries
    prediction_output = []
    future_db_entries = [] # List to hold tuples for bulk insertion
    for i, price in enumerate(y_pred):
        # Calculate the date for each future week
        future_date = (latest_date + timedelta(weeks=i + 1)).strftime("%Y-%m-%d")
        # Ensure price is not negative (optional, based on domain knowledge)
        cleaned_price = max(0.0, round(price, 2))

        prediction_output.append(
            {
                "prediction_index": i,
                "date": future_date,
                "price": cleaned_price,
            }
        )
        # Prepare data for insertion into the 'price' table
        # Use actual=0 to mark these as predictions
        future_db_entries.append(
            (future_date, data.region, crop_name, cleaned_price, 0)
        )

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.executemany(
                """
                INSERT OR IGNORE INTO price (date, region, crop, price, actual)
                VALUES (?, ?, ?, ?, ?)
                """,
                future_db_entries,
            )
            conn.commit()
            print(f"✅ Inserted {cursor.rowcount} new predicted price records.")
            # Note: rowcount only shows *new* inserts due to INSERT OR IGNORE
        except Exception as e:
             # Rollback in case of any error during insertion
            conn.rollback()
            print(f"❌ Error inserting predicted prices: {e}")
            raise HTTPException(status_code=500, detail=f"Database error while storing predictions: {e}")


    # 10. Return the prediction output
    return {
        "crop": crop_name,
        "region": data.region,
        "predictions": prediction_output,
    }