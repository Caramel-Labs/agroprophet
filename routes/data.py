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
        # This is unlikely with Pydantic, but added for completeness
        raise HTTPException(status_code=400, detail="Missing required fields.")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO price (date, region, crop, price) VALUES (?, ?, ?, ?)",
            (date, region, crop, price),
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
