from pydantic import BaseModel, Field


class PredictionPayload(BaseModel):
    crop: str = Field(..., example="Cantaloupe")
    region: str = Field(..., example="Valhalla")
