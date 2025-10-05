from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ForecastProduct(BaseModel):
    product_id: str
    product_name: Optional[str] = None
    quantity: float = Field(..., ge=0)
    dealer_id: Optional[str] = None
    dealer_name: Optional[str] = None

class ForecastInDB(BaseModel):
    salesman_id: str
    year: int = Field(..., ge=2020, le=2050)
    month: int = Field(..., ge=1, le=12)
    products: List[ForecastProduct] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ForecastCreateRequest(BaseModel):
    year: int = Field(..., ge=2020, le=2050)
    month: int = Field(..., ge=1, le=12)
    products: List[ForecastProduct] = []

class ForecastUpdateRequest(BaseModel):
    products: Optional[List[ForecastProduct]] = None

class ForecastResponse(BaseModel):
    id: str
    salesman_id: str
    salesman_name: Optional[str] = None
    year: int
    month: int
    products: List[ForecastProduct] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None