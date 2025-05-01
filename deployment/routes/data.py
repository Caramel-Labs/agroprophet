import sqlite3
from settings import DB_PATH
from fastapi import APIRouter
from fastapi import HTTPException
from payloads.price import PricePayload
from payloads.weather import WeatherPayload

# Setup prediction router
router = APIRouter(
    prefix="/data",
    tags=["Data"],
)

# --------------------------------
#             ROUTES
# --------------------------------


@router.post("/prices", tags=["Price"])
def store_price_data(payload: PricePayload):
    try:
        date = payload.date
        region = payload.region
        crop = payload.crop
        price = payload.priceData.price
    except Exception:
        raise HTTPException(status_code=400, detail="Missing required fields.")

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
            # No existing record: insert as new actual data
            cursor.execute(
                """
                INSERT INTO price (date, region, crop, price, actual)
                VALUES (?, ?, ?, ?, 1)
                """,
                (date, region, crop, price),
            )
            print(f"✅ New actual data inserted: {date}, {region}, {crop}, {price}")
        else:
            record_id, existing_price, is_actual = existing_row

            if is_actual == 0:
                # Existing predicted record: update with actual data
                price_diff = abs(price - existing_price)
                print(
                    f"🔁 Replacing predicted value with actual. Price diff: {price_diff:.2f}"
                )

                cursor.execute(
                    """
                    UPDATE price
                    SET price = ?, actual = 1
                    WHERE id = ?
                    """,
                    (price, record_id),
                )
            else:
                # Existing actual record
                if price != existing_price:
                    print(
                        f"⚠️ Actual price changed from {existing_price} to {price}. Updating."
                    )
                else:
                    print(
                        f"ℹ️ Actual price is the same as existing. Overwriting with {price} anyway."
                    )

                cursor.execute(
                    """
                    UPDATE price
                    SET price = ?
                    WHERE id = ?
                    """,
                    (price, record_id),
                )

        conn.commit()

    return {"message": "Price data saved successfully."}


@router.post("/weather", tags=["Weather"])
def store_weather_data(data: WeatherPayload):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
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
        conn.commit()

    return {"message": "Weather data saved successfully."}
