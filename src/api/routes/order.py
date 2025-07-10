# logic for making orders

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from api.deps.db import get_db
from api.models.sales_men import SalesManInDB, SalesManSimpleResponse
from api.models.dealers import DealerInDB
from api.models.products import ProductInDB, ProductSimpleResponse, ProductPackingResponse
from api.models.orders import OrderInDB
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

router = APIRouter(tags=["orders"])

# endpoint to fetch all salesman by state
@router.get("/salesmen", response_model=List[SalesManSimpleResponse])
async def get_salesmen_by_state(
    state: str = Query(..., min_length=1),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Database name: {db.name}")
    logging.info(f"Collection name: salesmen")
    logging.info(f"Searching for salesmen with state: '{state}'")
    
    # Check total documents in collection
    total_count = await db.salesmen.count_documents({})
    logging.info(f"Total salesmen in database: {total_count}")
    
    # Check documents with any state
    all_states = await db.salesmen.distinct("state")
    logging.info(f"All states in database: {all_states}")
    
    # Use case-insensitive regex for state matching and only select id and name
    salesmen_cursor = db.salesmen.find(
        {"state": {"$regex": f"^{state}$", "$options": "i"}},
        {"_id": 1, "name": 1}
    )
    salesmen = await salesmen_cursor.to_list(length=100)
    
    logging.info(f"Fetched {len(salesmen)} salesmen for state: {state}")
    logging.info(f"Salesmen data: {salesmen}")
    return salesmen

# Fetch all dealers given a salesman id
@router.get("/dealers/{salesman_id}")
async def get_dealers_by_salesman(
    salesman_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Searching for dealers with salesman_id: '{salesman_id}'")
    
    # Check total documents in dealers collection
    total_count = await db.dealers.count_documents({})
    logging.info(f"Total dealers in database: {total_count}")
    
    # Convert salesman_id to ObjectId and search for dealers
    dealers_cursor = db.dealers.find(
        {"sales_man_id": ObjectId(salesman_id)},
        {"_id": 1, "name": 1}  # Only return id and name
    )
    dealers = await dealers_cursor.to_list(length=100)
    
    # Convert ObjectId to string for JSON serialization
    dealers_response = []
    for dealer in dealers:
        dealers_response.append({
            "id": str(dealer["_id"]),
            "name": dealer["name"]
        })
    
    logging.info(f"Fetched {len(dealers_response)} dealers for salesman_id: {salesman_id}")
    logging.info(f"Dealers data: {dealers_response}")
    return dealers_response

# Fetch all products
@router.get("/products", response_model=List[ProductSimpleResponse])
async def get_all_products(
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info("Fetching all unique product names")
    
    # Get unique product names using MongoDB distinct
    unique_names = await db.products.distinct("name")
    # For each unique name, get one document to fetch its _id (first occurrence)
    products = []
    for name in unique_names:
        doc = await db.products.find_one({"name": name}, {"_id": 1, "name": 1})
        if doc:
            products.append(doc)
    
    logging.info(f"Fetched {len(products)} unique products")
    return products

# Fetch product packing information by product name
@router.get("/products/{product_name}/packing", response_model=List[ProductPackingResponse])
async def get_product_packing_by_name(
    product_name: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Fetching packing info for product_name: '{product_name}'")
    
    # Find all products with the same name
    products_cursor = db.products.find(
        {"name": product_name},
        {"_id": 1, "name": 1, "packing_size": 1, "bottles_per_case": 1, "bottle_volume": 1, "moq": 1}
    )
    products = await products_cursor.to_list(length=100)
    
    if not products:
        raise HTTPException(status_code=404, detail="No products found with that name")
    
    logging.info(f"Found {len(products)} products with name '{product_name}'")
    logging.info(f"Products packing info: {products}")
    return products

# Create an order document with order validation middleware
@router.post("/make-order", response_model=OrderInDB)
async def create_order(
    order: OrderInDB,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Insert order into DB
        order_dict = order.dict(by_alias=True)
        from datetime import datetime
        now = datetime.utcnow()
        order_dict.setdefault("created_at", now)
        order_dict.setdefault("updated_at", now)
        order_dict.setdefault("status", "pending")
        result = await db.orders.insert_one(order_dict)
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Order creation failed")
        order_dict["_id"] = result.inserted_id
        return order_dict
    except RequestValidationError as e:
        logging.error(f"Validation error while creating order: {e.errors()}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error while creating order: {str(e)}")
        raise

# Fetch product price by product id and quantity
@router.get("/products/{product_id}/price")
async def get_product_price(
    product_id: str,
    quantity: int = Query(..., gt=0),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Fetching price for product_id: '{product_id}' with quantity: {quantity}")
    product = await db.products.find_one(
        {"_id": ObjectId(product_id)},
        {"dealer_price_per_bottle": 1, "billing_price_per_bottle": 1, "mrp_per_bottle": 1, "name": 1}
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    price_per_bottle = product.get("billing_price_per_bottle") or product.get("dealer_price_per_bottle") or product.get("mrp_per_bottle")
    if price_per_bottle is None:
        raise HTTPException(status_code=400, detail="Product price not available")
    total_price = price_per_bottle * quantity
    logging.info(f"Product: {product.get('name')}, Unit price: {price_per_bottle}, Total price: {total_price}")
    return {
        "product_id": str(product_id),
        "product_name": product.get("name"),
        "unit_price": price_per_bottle,
        "quantity": quantity,
        "total_price": total_price
    }

# List all orders
@router.get("", response_model=List[OrderInDB])
async def list_all_orders(
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info("Fetching all orders")
    orders_cursor = db.orders.find({})
    orders = await orders_cursor.to_list(length=1000)
    logging.info(f"Fetched {len(orders)} orders")
    return orders