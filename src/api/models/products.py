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

# mongo product model
class ProductInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=3, max_length=100)  # e.g., Nexpro Nitro Plus
    category: str = Field(..., min_length=3, max_length=100)  # e.g., Bio-Stimulants / Micro-nutrients 18% GST
    packing_size: str = Field(..., min_length=1, max_length=50)  # e.g., 50x100 ML
    bottles_per_case: int = Field(..., ge=1)  # Number of bottles in packing size (e.g., 50 for 50x100 ML)
    bottle_volume: str = Field(..., min_length=1, max_length=20)  # Volume per bottle (e.g., 100 ML)
    moq: str = Field(..., min_length=1, max_length=50)  # e.g., one case
    dealer_price_per_bottle: float = Field(..., gt=0.0)  # Price per bottle
    gst_percentage: float = Field(..., ge=0.0)  # GST percentage (e.g., 18)
    billing_price_per_bottle: float = Field(..., gt=0.0)  # Dealer price + GST
    mrp_per_bottle: float = Field(..., gt=0.0)  # Maximum Retail Price per bottle
    product_details: Optional[str] = Field(default=None, max_length=200)  # e.g., Growth & overall plant health
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "_id": "60c72b2f9b1e8d001c8e4f3c",
                "name": "Nexpro Nitro Plus",
                "category": "Bio-Stimulants / Micro-nutrients 18% GST",
                "packing_size": "50x100 ML",
                "bottles_per_case": 50,
                "bottle_volume": "100 ML",
                "moq": "one case",
                "dealer_price_per_bottle": 72.00,
                "gst_percentage": 18.0,
                "billing_price_per_bottle": 85.00,
                "mrp_per_bottle": 149.00,
                "product_details": "Growth & overall plant health",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z"
            }
        }

# Simple model for product response with id, name and gst_percentage
class ProductSimpleResponse(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    gst_percentage: float

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3c",
                "name": "Nexpro Nitro Plus",
                "gst_percentage": 18.0
            }
        }

# Model for product packing information
class ProductPackingResponse(BaseModel):
    id: PyObjectId = Field(alias="_id")
    name: str
    packing_size: str
    bottles_per_case: int
    bottle_volume: str
    moq: str

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3c",
                "name": "Nexpro Nitro Plus",
                "packing_size": "50x100 ML",
                "bottles_per_case": 50,
                "bottle_volume": "100 ML",
                "moq": "one case"
            }
        }

# model for product response (to return to client)
class ProductResponse(BaseModel):
    id: PyObjectId
    name: str
    category: str
    packing_size: str
    bottles_per_case: int
    bottle_volume: str
    moq: str
    dealer_price_per_bottle: float
    gst_percentage: float
    billing_price_per_bottle: float
    mrp_per_bottle: float
    product_details: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "id": "60c72b2f9b1e8d001c8e4f3c",
                "name": "Nexpro Nitro Plus",
                "category": "Bio-Stimulants / Micro-nutrients 18% GST",
                "packing_size": "50x100 ML",
                "bottles_per_case": 50,
                "bottle_volume": "100 ML",
                "moq": "one case",
                "dealer_price_per_bottle": 72.00,
                "gst_percentage": 18.0,
                "billing_price_per_bottle": 85.00,
                "mrp_per_bottle": 149.00,
                "product_details": "Growth & overall plant health",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z"
            }
        }
