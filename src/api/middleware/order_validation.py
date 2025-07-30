"""
    validate orders
    1. check if dealer is under the salesman
    2. check if dealer is in same state as salesman"""

from fastapi import HTTPException, Depends
from bson import ObjectId
from api.models.dealers import DealerInDB
from api.models.sales_men import SalesManInDB
from motor.motor_asyncio import AsyncIOMotorDatabase

async def validate_order(
    dealer_id: ObjectId,
    salesman_id: ObjectId,
    db: AsyncIOMotorDatabase
):
    # fetch dealer and salesman from db
    dealer = await db.dealers.find_one({"_id": ObjectId(dealer_id)})
    salesman = await db.sales_men.find_one({"_id": ObjectId(salesman_id)})

    if not dealer or not salesman:
        raise HTTPException(status_code=404, detail="Dealer or Salesman not found")

    # check1 = if dealer is under salesman
    if str(dealer["sales_man_id"]) != str(salesman["_id"]):
        raise HTTPException(status_code=400, detail="Dealer is not under the Salesman")

    # check2 = if dealer is in same state as salesman
    if dealer.get("state") != salesman.get("state"):
        raise HTTPException(status_code=400, detail="Dealer is not in the same state as Salesman")

    return True  # validation passed
