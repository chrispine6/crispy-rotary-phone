from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from bson import ObjectId


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


class DirectorInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=12)
    state: Optional[str] = Field(default=None, max_length=50)
    firebase_uid: Optional[str] = Field(default=None)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "_id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "Dinesh Director",
                "email": "dinesh.director@example.com",
                "phone": "9123456780",
                "state": "Maharashtra",
                "firebase_uid": "firebase-uid-xyz",
                "active": True,
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z",
            }
        }


class DirectorResponse(BaseModel):
    id: PyObjectId
    name: str
    email: EmailStr
    phone: Optional[str]
    state: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "Dinesh Director",
                "email": "dinesh.director@example.com",
                "phone": "9123456780",
                "state": "Maharashtra",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z",
            }
        }


class DirectorSimpleResponse(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3a",
                "name": "Dinesh Director",
            }
        }
