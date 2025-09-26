
import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# Load environment variables from .env
load_dotenv()

MONGO_URI = os.getenv("MONGODB_URL")
DB_NAME = os.getenv("DB_NAME", "nexfarm_db")

async def main():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    salesmen = db.salesmen
    dealers = db.dealers

    async for salesman in salesmen.find({}):
        sid = salesman.get("_id")
        if not sid:
            continue
        # Find all dealers with sales_man_id matching this salesman's _id (as string or ObjectId)
        dealer_objs = await dealers.find({
            "$or": [
                {"sales_man_id": sid},
                {"sales_man_id": str(sid)}
            ]
        }).to_list(length=1000)
        dealer_ids = [d["_id"] for d in dealer_objs if "_id" in d]
        # Update the salesman document
        await salesmen.update_one({"_id": sid}, {"$set": {"dealers": dealer_ids}})
        print(f"Updated salesman {sid} with dealers: {dealer_ids}")

    print("Done populating dealers for all salesmen.")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())