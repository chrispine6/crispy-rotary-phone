#!/usr/bin/env python3
"""
Migration script to add credit_limit field to all existing dealer records.
Sets credit_limit to 100,000 for all dealers that don't have this field.
"""

import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import MONGODB_URL, DB_NAME

async def update_dealer_credit_limits():
    """Update all dealer records to include credit_limit field."""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    try:
        # Find all dealers that don't have credit_limit field
        dealers_without_credit_limit = await db.dealers.find(
            {"credit_limit": {"$exists": False}}
        ).to_list(length=1000)
        
        print(f"Found {len(dealers_without_credit_limit)} dealers without credit_limit field")
        
        if len(dealers_without_credit_limit) == 0:
            print("All dealers already have credit_limit field. No updates needed.")
            return
        
        # Update all dealers without credit_limit
        result = await db.dealers.update_many(
            {"credit_limit": {"$exists": False}},
            {"$set": {"credit_limit": 100000}}
        )
        
        print(f"Successfully updated {result.modified_count} dealer records with credit_limit: 100,000")
        
        # Verify the update
        total_dealers = await db.dealers.count_documents({})
        dealers_with_credit_limit = await db.dealers.count_documents(
            {"credit_limit": {"$exists": True}}
        )
        
        print(f"Verification: {dealers_with_credit_limit}/{total_dealers} dealers now have credit_limit field")
        
        # Show some sample updated records
        sample_dealers = await db.dealers.find({}).limit(3).to_list(length=3)
        print("\nSample dealer records after update:")
        for i, dealer in enumerate(sample_dealers, 1):
            print(f"{i}. Name: {dealer.get('name', 'N/A')}, Credit Limit: {dealer.get('credit_limit', 'N/A')}")
            
    except Exception as e:
        print(f"Error updating dealer credit limits: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    print("Starting dealer credit limit migration...")
    asyncio.run(update_dealer_credit_limits())
    print("Migration completed!")
