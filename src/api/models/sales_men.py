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
    def validate(cls, v, field=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema):
        return {"type": "string", "pattern": "^[a-fA-F0-9]{24}$"}


# mongo sales man model
class SalesManInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=12)
    state: Optional[str] = Field(default=None, max_length=50)
    dealers: list[str] = Field(default_factory=list)
    firebase_uid: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    admin: bool = Field(default=True)
    
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
                "firebase_uid": "firebase-uid-xyz",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z",
                "admin": True
            }
        }

# model for sales man response (to return to client)
class SalesManResponse(BaseModel):
    id: PyObjectId
    name: str
    email: EmailStr
    phone: Optional[str]
    state: Optional[str]
    dealers: list[str]
    firebase_uid: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "johndoe",
                "email": "john.doe@example.com",
                "phone": "1234567890",
                "state": "delhi",
                "dealers": ["dealer1", "dealer2"],
                "firebase_uid": "firebase-uid-xyz",
                "created_at": "2021-06-14T12:34:56.789Z",
            }
        }

# Simple model for salesman response with only id and name
class SalesManSimpleResponse(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "johndoe"
            }
        }

