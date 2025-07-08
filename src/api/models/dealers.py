from pydantic import BaseModel, Field, EmailStr
from typing import Optional
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

# mongo dealer model
class DealerInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=3, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=12)
    state: Optional[str] = Field(default=None, max_length=50)
    sales_man_id: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "_id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "Dealer One",
                "phone": "1234567890",
                "state": "delhi",
                "sales_man_id": "60c72b2f9b1e8d001c8e4f3b",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z"
            }
        }

# model for dealer response (to return to client)
class DealerResponse(BaseModel):
    id: PyObjectId
    name: str
    phone: Optional[str]
    state: Optional[str]
    sales_man_id: PyObjectId
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "Dealer One",
                "phone": "1234567890",
                "state": "delhi",
                "sales_man_id": "60c72b2f9b1e8d001c8e4f3b",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z"
            }
        }
