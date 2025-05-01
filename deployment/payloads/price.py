from pydantic import BaseModel


class PriceData(BaseModel):
    price: float


class PricePayload(BaseModel):
    date: str
    region: str
    crop: str
    priceData: PriceData
