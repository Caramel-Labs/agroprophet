from pydantic import BaseModel, Field


class PricePredictionPayload(BaseModel):
    date: str = Field(..., example="2025-05-01")
    region: str = Field(..., example="Valhalla")
    type: str = Field(..., example="Fruit")
    commodity: str = Field(..., example="Cantaloupe")
    price: float = Field(..., example=86.4)
