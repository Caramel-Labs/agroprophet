from pydantic import BaseModel


class WeatherData(BaseModel):
    rainfall: float | None = None
    humidity: float | None = None
    temp: float | None = None


class WeatherPayload(BaseModel):
    date: str
    region: str
    weatherData: WeatherData
