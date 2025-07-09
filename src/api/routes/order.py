# logic for making orders

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from src.api.models.dealers import DealerInDB
from src.api.models.products import ProductInDB
from src.api.models.orders import OrderInDB
from src.api.middleware.order_validation import validate_order

router = APIRouter(prefix="/orders", tags=["orders"])

# Fetch all dealers given a salesman id
@router.get("/dealers/{salesman_id}", response_model=List[DealerInDB])
async def get_dealers_by_salesman(
    salesman_id: str,
    db: AsyncIOMotorDatabase = Depends()
):
    dealers_cursor = db.dealers.find({"sales_man_id": ObjectId(salesman_id)})
    dealers = await dealers_cursor.to_list(length=100)
    return dealers

# Fetch all products
@router.get("/products", response_model=List[ProductInDB])
async def get_all_products(
    db: AsyncIOMotorDatabase = Depends()
):
    products_cursor = db.products.find({})
    products = await products_cursor.to_list(length=100)
    return products

# Create an order document with order validation middleware
@router.post("/", response_model=OrderInDB)
async def create_order(
    order: OrderInDB,
    db: AsyncIOMotorDatabase = Depends(),
    _=Depends(lambda: validate_order(order.dealer_id, order.salesman_id, db))
):
    # Insert order into DB
    order_dict = order.dict(by_alias=True)
    result = await db.orders.insert_one(order_dict)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Order creation failed")
    order_dict["_id"] = result.inserted_id
    return order_dict
