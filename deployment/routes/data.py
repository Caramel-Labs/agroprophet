# routes/data.py

import sqlite3
import math
import os
import joblib
import numpy as np
import pandas as pd 
from fastapi import APIRouter, HTTPException, BackgroundTasks
from payloads.price import PricePayload
from payloads.weather import WeatherPayload
from settings import DB_PATH, RMSE_THRESHOLD, MIN_ERROR_POINTS, MODELS_PATH, FRUITS, VEGETABLES 
from datetime import datetime, timedelta

from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor
from sklearn.multioutput import MultiOutputRegressor


# Setup data router
router = APIRouter(
    prefix="/data",
    tags=["Data"],
)

# --------------------------------
#         HELPER FUNCTIONS
# --------------------------------

def determine_crop_type(crop_name: str):
    """Infers the crop type (Fruit or Vegetable) from the crop name."""
    if crop_name in FRUITS:
        return "Fruit"
    elif crop_name in VEGETABLES:
        return "Vegetable"
    else:
        # This case should ideally be caught earlier, but good for robustness
        print(f"Warning: Unknown crop '{crop_name}' encountered during retraining.")
        return None # Or raise an error if unknown crops shouldn't exist


def prepare_retraining_data(db_data: list, region: str, crop: str, crop_type: str, loaded_encoder: LabelEncoder):
    """
    Prepares data fetched from the database for model retraining,
    replicating the logic of the original prepare_dataset function.

    Args:
        db_data: List of tuples (date, price) fetched from the database.
                 Assumes data is already filtered for the specific region and crop.
        region: The region name.
        crop: The specific crop name (e.g., 'Apple').
        crop_type: The type of crop (e.g., 'Fruit').
        loaded_encoder: The pre-fitted LabelEncoder for this crop type.

    Returns:
        Tuple (X, y) of numpy arrays ready for model training, or (None, None) if insufficient data.
        X: Features (commodity_enc + lags)
        y: Targets (leads)
    """
    if not db_data:
        print("No data provided for retraining preparation.")
        return None, None

    # Convert list of tuples to DataFrame, mimicking original column names
    # Add dummy columns for 'Region' and 'Type' as they are used for filtering in original prepare_dataset
    # and 'Commodity' to match the encoder's expected input.
    df = pd.DataFrame(db_data, columns=['Date', 'Price per Unit (Silver Drachma/kg)'])
    df['Region'] = region
    df['Type'] = crop_type
    df['Commodity'] = crop # Add the specific crop name

    # Replicate the data preparation steps from the original prepare_dataset
    df = (
        df.assign(Date=lambda d: pd.to_datetime(d['Date']))
          .sort_values(['Commodity','Date']) # Sort by commodity and date as in original
    )

    # Use the loaded encoder to transform the 'Commodity' column
    # The encoder should already be fitted on all commodities for this crop type
    try:
        df['commodity_enc'] = loaded_encoder.transform(df['Commodity'])
    except ValueError as e:
        print(f"Error transforming commodity '{crop}' with loaded encoder: {e}. This crop might not have been in the original training data.")
        return None, None # Cannot proceed if encoding fails
    except Exception as e:
         print(f"Unexpected error during commodity encoding: {e}")
         return None, None


    # Build lags (1-4) and leads (1-4)
    # Use the exact column name from the original script for price
    price_col = 'Price per Unit (Silver Drachma/kg)'
    for lag in [1,2,3,4]:
        # Groupby 'Commodity' before shifting, as in original
        df[f'lag_{lag}'] = df.groupby('Commodity')[price_col].shift(lag)
    for lead in [1,2,3,4]:
         # Groupby 'Commodity' before shifting, as in original
        df[f'lead_{lead}'] = df.groupby('Commodity')[price_col].shift(-lead)


    # Define columns used for dropping NaNs
    lag_cols  = [f'lag_{l}'  for l in [1,2,3,4]]
    lead_cols = [f'lead_{l}' for l in [1,2,3,4]]
    # Drop rows with NaNs in feature/target columns, including the encoded commodity
    df_clean = df.dropna(subset=lag_cols + lead_cols + ['commodity_enc'])

    # Check if enough data remains after dropping NaNs
    if df_clean.shape[0] < MIN_ERROR_POINTS: # Use MIN_ERROR_POINTS or a separate retraining threshold
         print(f"Insufficient data ({df_clean.shape[0]} rows) after preparing features/targets for {region}/{crop}. Need at least {MIN_ERROR_POINTS} training samples.")
         return None, None


    # Separate features (X) and targets (y)
    # Features: encoded commodity + lags
    X = df_clean[['commodity_enc'] + lag_cols]
    # Targets: leads
    y = df_clean[lead_cols]

    print(f"Prepared training data for {region}/{crop}: X shape {X.shape}, y shape {y.shape}")

    return X.to_numpy(), y.to_numpy() # Return as numpy arrays


def perform_actual_retraining(region: str, crop: str):
    """
    Background task function to perform the actual model retraining
    for a specific region and crop.
    """
    print(f"🏋️‍♂️ Starting retraining for model: {region} / {crop}")

    # Determine crop type to load the correct model file
    crop_type = determine_crop_type(crop)
    if crop_type is None:
        print(f"❌ Retraining failed for {region}/{crop}: Could not determine crop type.")
        return

    model_filename = f"{region}__{crop_type}.joblib".replace(" ", "_")
    model_path = os.path.join(MODELS_PATH, model_filename)

    if not os.path.exists(model_path):
        print(f"❌ Retraining failed for {region}/{crop}: Model file not found at {model_path}.")
        return

    try:
        # --- 1. Load Existing Model and Encoder ---
        # We need the existing encoder to correctly encode the commodity during data prep
        print(f"Loading existing model data from {model_path}...")
        model_data = joblib.load(model_path)
        existing_model = model_data["model"] # We load the model just to confirm structure, but will train a new one
        loaded_encoder: LabelEncoder = model_data["label_encoder"]
        print("✅ Existing model data and encoder loaded.")

    except Exception as e:
        print(f"❌ Error loading existing model data or encoder for {region}/{crop}: {e}")
        return

    try:
        # --- 2. Fetch All Actual Data for Retraining ---
        # Fetch all actual price data for this specific region and crop from the database.
        # This includes historical data imported from CSV and new data collected via the API.
        print(f"Fetching all actual price data for {region}/{crop} from database...")
        with sqlite3.connect(DB_PATH) as conn:
             cursor = conn.cursor()
             cursor.execute(
                 """
                 SELECT date, price FROM price
                 WHERE region = ? AND crop = ? AND actual = 1
                 ORDER BY date ASC
                 """,
                 (region, crop),
             )
             actual_price_data = cursor.fetchall()

        if not actual_price_data:
             print(f"⚠️ No actual data found for {region}/{crop} in the database. Cannot retrain.")
             return

        print(f"Fetched {len(actual_price_data)} actual data points.")

        # --- 3. Prepare Data for Training ---
        # Use the helper function to prepare features (X) and targets (y)
        # using the fetched data and the loaded encoder.
        X_train, y_train = prepare_retraining_data(actual_price_data, region, crop, crop_type, loaded_encoder)

        if X_train is None or y_train is None:
            # prepare_retraining_data will print specific reasons for failure
            print(f"❌ Data preparation failed or insufficient data for retraining {region}/{crop}. Skipping retraining.")
            return

        # --- 4. Train the Model ---
        # Instantiate the same model architecture and parameters as in original training
        print(f"Training {region}/{crop} model with {X_train.shape[0]} samples...")
        try:
            # Re-instantiate the model with the same parameters
            model = MultiOutputRegressor(
                XGBRegressor(objective='reg:squarederror', n_estimators=1000)
            )
            model.fit(X_train, y_train) # Fit the model on the prepared data

            print(f"✅ Model training complete for {region}/{crop}.")

        except Exception as e:
            print(f"❌ Error during model training for {region}/{crop}: {e}")
            return


        # --- 5. Save the New Model ---
        # Save the newly trained model and the *loaded* label encoder, overwriting the old file.
        try:
            # Ensure the models directory exists (should be done by init_db or deployment setup, but good check)
            os.makedirs(MODELS_PATH, exist_ok=True)

            # Save the updated model and the *same* label encoder together
            joblib.dump({'model': model, 'label_encoder': loaded_encoder}, model_path)

            print(f"✅ Successfully saved updated model: {model_path}")

        except Exception as e:
            print(f"❌ Error saving the retrained model for {region}/{crop}: {e}")


    except Exception as e:
        # Catch any other unexpected errors during the background task
        print(f"❌ An unexpected error occurred during retraining for {region}/{crop}: {e}")


def calculate_rolling_rmse_and_check(conn, date: str, region: str, crop: str, background_tasks: BackgroundTasks):
    """
    Calculates the 3-month rolling RMSE for a specific region/crop
    and adds a retraining task if the threshold is exceeded.
    """
    cursor = conn.cursor()
    current_date = datetime.strptime(date, "%Y-%m-%d")
    three_months_ago = current_date - timedelta(weeks=13) # Approx 3 months

    cursor.execute(
        """
        SELECT squared_error FROM prediction_errors
        WHERE region = ? AND crop = ? AND date >= ? AND date <= ?
        ORDER BY date DESC
        """,
        (region, crop, three_months_ago.strftime("%Y-%m-%d"), date),
    )
    errors = cursor.fetchall()

    num_error_points = len(errors)

    if num_error_points < MIN_ERROR_POINTS:
        print(f"ℹ️ Not enough error points ({num_error_points}) for {region}/{crop} in rolling window ending {date}. Need {MIN_ERROR_POINTS} to check RMSE.")
        return None # Not enough data to calculate meaningful RMSE

    sum_squared_errors = sum(e[0] for e in errors)
    mean_squared_error = sum_squared_errors / num_error_points
    rmse = math.sqrt(mean_squared_error)

    print(f"📊 Rolling RMSE for {region}/{crop} (last {num_error_points} points ending {date}): {rmse:.2f}")

    if rmse > RMSE_THRESHOLD:
        print(f"🚨 RMSE ({rmse:.2f}) for {region}/{crop} exceeds threshold ({RMSE_THRESHOLD}). Scheduling retraining!")
        # --- Add the retraining task to be run in the background ---
        # Pass region and crop name to the background task
        background_tasks.add_task(perform_actual_retraining, region, crop)
        # -----------------------------------------------------------
    else:
         print(f"✅ Rolling RMSE ({rmse:.2f}) for {region}/{crop} is within threshold.")


    return rmse


# --------------------------------
#             ROUTES
# --------------------------------

# Add BackgroundTasks as a parameter to the route handler
@router.post("/prices", tags=["Price"])
async def store_price_data(payload: PricePayload, background_tasks: BackgroundTasks):
    """
    Stores or updates price data. If an actual price replaces a prediction,
    calculates and logs the squared error and checks rolling RMSE,
    scheduling retraining in the background if needed.
    """
    try:
        date = payload.date
        region = payload.region
        crop = payload.crop
        price = payload.priceData.price # This is the incoming price (always actual)
    except Exception:
        raise HTTPException(status_code=400, detail="Missing required fields or invalid payload structure.")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Check if a record already exists for the same date, region, and crop
        cursor.execute(
            """
            SELECT id, price, actual FROM price
            WHERE date = ? AND region = ? AND crop = ?
            """,
            (date, region, crop),
        )
        existing_row = cursor.fetchone()

        if existing_row is None:
            # Case 1: No existing record - Insert as new actual data
            cursor.execute(
                """
                INSERT INTO price (date, region, crop, price, actual)
                VALUES (?, ?, ?, ?, 1)
                """,
                (date, region, crop, price),
            )
            print(f"✅ New actual data inserted: {date}, {region}, {crop}, Price: {price}")
            # No prediction was replaced, so no error calculation or RMSE check needed here.

        else:
            # Case 2: Record already exists
            record_id, existing_price, is_actual = existing_row
            incoming_actual_price = price # The price from the payload is always actual

            if is_actual == 0:
                # Case 2a: Existing predicted record (actual = 0) - Calculate error, update to actual
                predicted_price = existing_price
                squared_error = (incoming_actual_price - predicted_price)**2

                print(
                    f"🔁 Replacing predicted value ({predicted_price:.2f}) with actual ({incoming_actual_price:.2f}) for {date}, {region}, {crop}. Squared Error: {squared_error:.2f}"
                )

                # Insert the squared error into the prediction_errors table
                try:
                    cursor.execute(
                        """
                        INSERT INTO prediction_errors (date, region, crop, squared_error)
                        VALUES (?, ?, ?, ?)
                        """,
                        (date, region, crop, squared_error),
                    )
                    print(f"✅ Squared error logged for {date}, {region}, {crop}")
                except Exception as e:
                     # Log the error but don't fail the price update
                    print(f"❌ Error logging squared error for {date}, {region}, {crop}: {e}")


                # Update the price record to the new actual price and set actual = 1
                cursor.execute(
                    """
                    UPDATE price
                    SET price = ?, actual = 1
                    WHERE id = ?
                    """,
                    (incoming_actual_price, record_id),
                )
                print(f"✅ Price record updated to actual.")

                # --- Call the RMSE check function and pass BackgroundTasks ---
                # This function will add perform_actual_retraining to background_tasks if needed
                calculate_rolling_rmse_and_check(conn, date, region, crop, background_tasks)
                # ---------------------------------------------------------------------------

            else:
                # Case 2b: Existing actual record (actual = 1) - Just update if price changed
                if incoming_actual_price != existing_price:
                    print(
                        f"⚠️ Actual price for {date}, {region}, {crop} changed from {existing_price} to {incoming_actual_price}. Updating."
                    )
                    # No prediction was involved, so no error calculation for model performance here.
                else:
                    print(
                        f"ℹ️ Actual price for {date}, {region}, {crop} is the same as existing ({existing_price}). Overwriting anyway."
                    )

                # Update the price record (actual remains 1)
                cursor.execute(
                    """
                    UPDATE price
                    SET price = ?
                    WHERE id = ?
                    """,
                    (incoming_actual_price, record_id),
                )
                print(f"✅ Price record updated.")

        conn.commit()

    return {"message": "Price data saved successfully."}


@router.post("/weather", tags=["Weather"])
def store_weather_data(data: WeatherPayload):
    """Stores or updates weather data."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Check if a weather record for this date and region already exists
        cursor.execute(
            """
            SELECT id FROM weather WHERE date = ? AND region = ?
            """,
            (data.date, data.region),
        )
        existing_row = cursor.fetchone()

        if existing_row:
            # If exists, update
            print(f"ℹ️ Weather data for {data.date}, {data.region} already exists. Updating.")
            cursor.execute(
                """
                UPDATE weather
                SET rainfall = ?, humidity = ?, temp = ?
                WHERE id = ?
                """,
                (data.weatherData.rainfall, data.weatherData.humidity, data.weatherData.temp, existing_row[0]),
            )
        else:
            # If not exists, insert
            cursor.execute(
                """
                INSERT INTO weather (date, region, rainfall, humidity, temp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    data.date,
                    data.region,
                    data.weatherData.rainfall,
                    data.weatherData.humidity,
                    data.weatherData.temp,
                ),
            )
            print(f"✅ New weather data inserted for {data.date}, {data.region}")

        conn.commit()

    return {"message": "Weather data saved successfully."}
