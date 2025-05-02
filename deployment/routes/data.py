# routes/data.py

import sqlite3
import math # Need for sqrt
from settings import DB_PATH, RMSE_THRESHOLD, MIN_ERROR_POINTS # Import new settings
from fastapi import APIRouter
from fastapi import HTTPException
from payloads.price import PricePayload # Assuming this Pydantic model exists
from payloads.weather import WeatherPayload # Assuming this Pydantic model exists
from datetime import datetime, timedelta # Need for date calculations

# Placeholder Import for Retraining Trigger (replace with your actual module)
# from your_retraining_module import trigger_retrain_model

# Setup data router
router = APIRouter(
    prefix="/data",
    tags=["Data"],
)

# --------------------------------
#         HELPER FUNCTIONS
# --------------------------------

def calculate_rolling_rmse_and_check(conn, date: str, region: str, crop: str):
    """
    Calculates the 3-month rolling RMSE for a specific region/crop
    ending on the given date and triggers retraining if the threshold is exceeded.
    """
    cursor = conn.cursor()
    current_date = datetime.strptime(date, "%Y-%m-%d")
    # Define the rolling window: from 3 months ago up to (and including) the current date
    three_months_ago = current_date - timedelta(weeks=13) # Approx 3 months

    cursor.execute(
        """
        SELECT squared_error FROM prediction_errors
        WHERE region = ? AND crop = ? AND date >= ? AND date <= ?
        ORDER BY date DESC -- Ordering by date is good for clarity but not strictly needed for sum/count
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
        print(f"🚨 RMSE ({rmse:.2f}) for {region}/{crop} exceeds threshold ({RMSE_THRESHOLD}). Retraining needed!")
        # --- Trigger Retraining Process ---
        # This part depends on how your retraining is set up.
        # You might log this, add a task to a queue, or call another function.
        # This function *does not* perform the retraining itself.
        try:
            # Replace with your actual retraining trigger call
            # trigger_retrain_model(region, crop)
            print(f"Triggering retraining for {region}/{crop}...") # Placeholder log
            pass # Add your actual trigger logic here
        except Exception as e:
            print(f"❌ Failed to trigger retraining for {region}/{crop}: {e}")
        # ----------------------------------
    else:
         print(f"✅ Rolling RMSE ({rmse:.2f}) for {region}/{crop} is within threshold.")


    return rmse


# --------------------------------
#             ROUTES
# --------------------------------


@router.post("/prices", tags=["Price"])
def store_price_data(payload: PricePayload):
    """
    Stores or updates price data. If an actual price replaces a prediction,
    calculates and logs the squared error and checks rolling RMSE.
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
        # We select 'actual' and 'price' (which would be the predicted price if actual=0)
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

                # --- Call the RMSE check function after logging error and updating price ---
                calculate_rolling_rmse_and_check(conn, date, region, crop)
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