# order model to register orders in the database

from pydantic import BaseModel, Field
from typing import Optional, List
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

class ProductOrder(BaseModel):
    product_id: str
    quantity: int
    price: float  # Base line total BEFORE discount for this product line
    product_name: Optional[str] = None
    discount_pct: Optional[float] = 0  # New: per-line discount percentage (0-30)
    discounted_price: Optional[float] = None  # New: line total AFTER discount (derived client-side)

# mongo order model
class OrderInDB(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    state: str
    salesman_id: str
    dealer_id: str
    products: List[ProductOrder] = Field(default_factory=list)
    total_price: float
    status: Optional[str] = Field(default="pending")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    discount: Optional[float] = Field(default=0)
    discounted_total: Optional[float] = Field(default=None)
    discount_status: Optional[str] = Field(default="approved")  # "pending" if discount > 0, else "approved"

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "_id": "60c72b2f9b1e8d001c8e4f3d",
                "state": "AP",
                "salesman_id": "60c72b2f9b1e8d001c8e4f3b",
                "dealer_id": "60c72b2f9b1e8d001c8e4f3a",
                "products": [
                    {
                        "product_id": "60c72b2f9b1e8d001c8e4f3c",
                        "quantity": 2,
                        "price": 8500,
                        "product_name": "Nexpro Nitro Plus",
                        "discount_pct": 10,
                        "discounted_price": 7650
                    }
                ],
                "total_price": 17000,
                "discount": 10,
                "discounted_total": 15300,
                "status": "pending",
                "discount_status": "pending",
                "created_at": "2021-06-14T12:34:56.789Z",
                "updated_at": "2021-06-14T12:34:56.789Z"
            }
        }