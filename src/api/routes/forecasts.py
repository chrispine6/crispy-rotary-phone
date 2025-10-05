# Forecast routes for sales forecasting

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from datetime import datetime
from api.deps.db import get_db
from api.models.forecasts import ForecastInDB, ForecastCreateRequest, ForecastUpdateRequest, ForecastResponse

router = APIRouter(tags=["forecasts"])

# Function to clean ObjectId fields from MongoDB documents
def clean_object_ids(obj):
    if isinstance(obj, dict):
        return {k: clean_object_ids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_object_ids(v) for v in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

# Create or update a forecast for current user
@router.post("/forecasts")
async def create_or_update_forecast(
    forecast_data: ForecastCreateRequest,
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Resolve salesman_id from uid or email
        salesman_id = None
        if uid:
            salesman_doc = await db.salesmen.find_one({"firebase_uid": uid})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        if not salesman_id and email:
            import re
            pattern = f"^{re.escape(email)}$"
            salesman_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        
        if not salesman_id:
            raise HTTPException(status_code=404, detail="Salesman not found")
        
        # Process products
        processed_products = []
        
        for product in forecast_data.products:
            # Get product details
            product_doc = None
            if len(product.product_id) == 24:
                try:
                    product_doc = await db.products.find_one({"_id": ObjectId(product.product_id)})
                except Exception:
                    product_doc = None
            if not product_doc:
                product_doc = await db.products.find_one({"_id": product.product_id})
            
            product_name = product_doc.get("name", "") if product_doc else ""
            
            # Get dealer name if dealer_id provided
            dealer_name = ""
            if product.dealer_id:
                dealer_doc = None
                if len(product.dealer_id) == 24:
                    try:
                        dealer_doc = await db.dealers.find_one({"_id": ObjectId(product.dealer_id)})
                    except Exception:
                        dealer_doc = None
                if not dealer_doc:
                    dealer_doc = await db.dealers.find_one({"_id": product.dealer_id})
                dealer_name = dealer_doc.get("name", "") if dealer_doc else ""
            
            processed_products.append({
                "product_id": product.product_id,
                "product_name": product_name,
                "quantity": product.quantity,
                "dealer_id": product.dealer_id,
                "dealer_name": dealer_name
            })
        
        # Check if forecast already exists for this salesman/year/month
        existing = await db.forecasts.find_one({
            "salesman_id": salesman_id,
            "year": forecast_data.year,
            "month": forecast_data.month
        })
        
        now = datetime.utcnow()
        if existing:
            # Update existing forecast
            update_data = {
                "products": processed_products,
                "updated_at": now
            }
            await db.forecasts.update_one(
                {"_id": existing["_id"]},
                {"$set": update_data}
            )
            forecast_id = str(existing["_id"])
        else:
            # Create new forecast
            forecast_doc = {
                "salesman_id": salesman_id,
                "year": forecast_data.year,
                "month": forecast_data.month,
                "products": processed_products,
                "created_at": now,
                "updated_at": now
            }
            result = await db.forecasts.insert_one(forecast_doc)
            forecast_id = str(result.inserted_id)
        
        return {"id": forecast_id, "message": "Forecast saved successfully"}
        
    except Exception as e:
        logging.error(f"Error creating/updating forecast: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Get forecasts for current user
@router.get("/forecasts", response_model=List[ForecastResponse])
async def get_my_forecasts(
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    year: int | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Resolve salesman_id from uid or email
        salesman_id = None
        if uid:
            salesman_doc = await db.salesmen.find_one({"firebase_uid": uid})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        if not salesman_id and email:
            import re
            pattern = f"^{re.escape(email)}$"
            salesman_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        
        if not salesman_id:
            return []
        
        # Build query
        query = {"salesman_id": salesman_id}
        if year:
            query["year"] = year
            
        forecasts_cursor = db.forecasts.find(query).sort([("year", -1), ("month", -1)])
        forecasts = await forecasts_cursor.to_list(length=100)
        
        # Get salesman name
        salesman_name = salesman_doc.get("name", "") if 'salesman_doc' in locals() else ""
        
        result = []
        for forecast in forecasts:
            result.append(ForecastResponse(
                id=str(forecast["_id"]),
                salesman_id=forecast["salesman_id"],
                salesman_name=salesman_name,
                year=forecast["year"],
                month=forecast["month"],
                products=forecast.get("products", []),
                created_at=forecast.get("created_at"),
                updated_at=forecast.get("updated_at")
            ))
        
        return result
        
    except Exception as e:
        logging.error(f"Error fetching forecasts: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Get forecasts for all salesmen (director/admin only)
@router.get("/admin/forecasts", response_model=List[ForecastResponse])
async def get_all_forecasts(
    year: int | None = Query(default=None),
    salesman_id: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Build query
        query = {}
        if year:
            query["year"] = year
        if salesman_id:
            query["salesman_id"] = salesman_id
            
        forecasts_cursor = db.forecasts.find(query).sort([("year", -1), ("month", -1)])
        forecasts = await forecasts_cursor.to_list(length=1000)
        
        result = []
        for forecast in forecasts:
            # Get salesman name
            salesman_name = ""
            sid = forecast["salesman_id"]
            if sid:
                if len(sid) == 24:
                    try:
                        salesman_doc = await db.salesmen.find_one({"_id": ObjectId(sid)})
                    except Exception:
                        salesman_doc = None
                else:
                    salesman_doc = await db.salesmen.find_one({"_id": sid})
                salesman_name = salesman_doc.get("name", "") if salesman_doc else ""
            
            result.append(ForecastResponse(
                id=str(forecast["_id"]),
                salesman_id=forecast["salesman_id"],
                salesman_name=salesman_name,
                year=forecast["year"],
                month=forecast["month"],
                products=forecast.get("products", []),
                created_at=forecast.get("created_at"),
                updated_at=forecast.get("updated_at")
            ))
        
        return result
        
    except Exception as e:
        logging.error(f"Error fetching all forecasts: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Delete a forecast
@router.delete("/forecasts/{forecast_id}")
async def delete_forecast(
    forecast_id: str,
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Resolve salesman_id from uid or email
        salesman_id = None
        if uid:
            salesman_doc = await db.salesmen.find_one({"firebase_uid": uid})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        if not salesman_id and email:
            import re
            pattern = f"^{re.escape(email)}$"
            salesman_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        
        if not salesman_id:
            raise HTTPException(status_code=404, detail="Salesman not found")
        
        # Ensure user can only delete their own forecasts
        try:
            forecast_obj_id = ObjectId(forecast_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid forecast ID")
            
        forecast = await db.forecasts.find_one({"_id": forecast_obj_id, "salesman_id": salesman_id})
        if not forecast:
            raise HTTPException(status_code=404, detail="Forecast not found")
        
        await db.forecasts.delete_one({"_id": forecast_obj_id})
        return {"message": "Forecast deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting forecast: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")