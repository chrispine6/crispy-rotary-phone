# order model to register orders in the database

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from bson import ObjectId

# custom PyObjectId class for mongodb objectid validation
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

# mongo order model
class OrderInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    salesman_id: PyObjectId
    dealer_id: PyObjectId
    product_id: PyObjectId
    price: float
    state: str
    status: Literal["approved", "discarded"] = "approved"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    remarks: Optional[str] = None

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "_id": "60c72b2f9b1e8d001c8e4f3d",
                "salesman_id": "60c72b2f9b1e8d001c8e4f3a",
                "dealer_id": "60c72b2f9b1e8d001c8e4f3b",
                "product_id": "60c72b2f9b1e8d001c8e4f3c",
                "price": 1000.0,
                "state": "delhi",
                "status": "approved",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z",
                "remarks": "Urgent delivery"
            }
        }

