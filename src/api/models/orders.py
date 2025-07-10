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
    def validate(cls, v, *args, **kwargs):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema):
        return {"type": "string", "pattern": "^[a-fA-F0-9]{24}$"}

# mongo order model
class OrderInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    salesman_id: PyObjectId
    dealer_id: PyObjectId
    product_id: PyObjectId
    quantity: int
    price: float
    state: str
    status: Literal["pending", "approved", "discarded"] = "pending"
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
                "quantity": 10,
                "price": 1000.0,
                "state": "delhi",
                "status": "pending",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z",
                "remarks": "Urgent delivery"
            }
        }