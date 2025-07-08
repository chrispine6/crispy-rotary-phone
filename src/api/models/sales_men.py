from pydantic import BaseModel
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


# mongo sales man model
class SalesManInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., mi_length=3, max_length=50)
    email: EmailStr
    phone: str = Field(default=None, max_length=12)
    state: str = Field(default=None, max_length=50)
    dealers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "_id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "johndoe",
                "email": "john.doe@example.com",
                "phone": "1234567890",
                "state": "delhi",
                "dealers": ["dealer1", "dealer2"],
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z"
            }
        }

# model for sales man response (to return to client)
class SalesManResponse(BaseModel):
    id: PyObjectId
    name: str
    email: EmailStr
    phone: str
    state: str
    dealers: list[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "johndoe",
                "email": "john.doe@example.com"
                "phone": "1234567890",
                "state": "delhi",
                "dealers": ["dealer1", "dealer2"],
                "created_at": "2021-06-14T12:34:56.789Z",
            }
        }

