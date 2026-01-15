"""
Script to clear Firebase UIDs and all order data.
WARNING: This will permanently delete data!
"""

import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection details
MONGO_URI = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://nexfarm_admin:sgFeiUpVjWwuv84W@cluster0.aicbbge.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = "nexfarm_db"

async def clear_firebase_uids():
    """Clear all Firebase UIDs from salesmen, sales_managers, and directors."""
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DB_NAME]
        
        print("\n" + "="*60)
        print("CLEARING FIREBASE UIDs")
        print("="*60)
        
        # Clear salesmen firebase_uid
        result_salesmen = await db.salesmen.update_many({}, {"$unset": {"firebase_uid": ""}})
        print(f"✓ Salesmen: Matched {result_salesmen.matched_count}, Modified {result_salesmen.modified_count}")
        
        # Clear sales_managers firebase_uid
        result_managers = await db.sales_managers.update_many({}, {"$unset": {"firebase_uid": ""}})
        print(f"✓ Sales Managers: Matched {result_managers.matched_count}, Modified {result_managers.modified_count}")
        
        # Clear directors firebase_uid
        result_directors = await db.directors.update_many({}, {"$unset": {"firebase_uid": ""}})
        print(f"✓ Directors: Matched {result_directors.matched_count}, Modified {result_directors.modified_count}")
        
        total_modified = (
            result_salesmen.modified_count + 
            result_managers.modified_count + 
            result_directors.modified_count
        )
        
        print("\n" + "="*60)
        print(f"TOTAL: {total_modified} Firebase UIDs cleared")
        print("="*60)
        
        client.close()
        return total_modified
        
    except Exception as e:
        print(f"\n❌ Error clearing Firebase UIDs: {str(e)}")
        raise

async def clear_all_orders():
    """Delete all orders from the database."""
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DB_NAME]
        
        # First, count orders
        order_count = await db.orders.count_documents({})
        
        if order_count == 0:
            print("\n" + "="*60)
            print("No orders found in the database.")
            print("="*60)
            client.close()
            return 0
        
        print("\n" + "="*60)
        print("CLEARING ALL ORDERS")
        print("="*60)
        print(f"Found {order_count} orders in the database")
        
        # Confirm deletion
        confirm = input(f"\n⚠️  ARE YOU SURE you want to delete ALL {order_count} orders? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("\n❌ Order deletion cancelled.")
            client.close()
            return 0
        
        # Delete all orders
        result = await db.orders.delete_many({})
        
        print(f"\n✓ Successfully deleted {result.deleted_count} orders")
        print("="*60)
        
        client.close()
        return result.deleted_count
        
    except Exception as e:
        print(f"\n❌ Error clearing orders: {str(e)}")
        raise

async def main():
    """Main function to clear Firebase UIDs and orders."""
    print("\n" + "="*60)
    print("DATA CLEARING SCRIPT")
    print("="*60)
    print("This script will:")
    print("1. Clear all Firebase UIDs from salesmen, sales managers, and directors")
    print("2. Delete all orders from the database")
    print("\n⚠️  WARNING: This operation cannot be undone!")
    print("="*60)
    
    proceed = input("\nDo you want to proceed? (yes/no): ")
    
    if proceed.lower() != 'yes':
        print("\n❌ Operation cancelled.")
        return
    
    try:
        # Ask what to clear
        print("\nWhat would you like to clear?")
        print("1. Clear Firebase UIDs only")
        print("2. Clear all orders only")
        print("3. Clear both Firebase UIDs and orders")
        
        choice = input("\nEnter your choice (1/2/3): ").strip()
        
        uids_cleared = 0
        orders_deleted = 0
        
        if choice in ['1', '3']:
            uids_cleared = await clear_firebase_uids()
        
        if choice in ['2', '3']:
            orders_deleted = await clear_all_orders()
        
        # Summary
        print("\n" + "="*60)
        print("OPERATION SUMMARY")
        print("="*60)
        if choice in ['1', '3']:
            print(f"✓ Firebase UIDs cleared: {uids_cleared}")
        if choice in ['2', '3']:
            print(f"✓ Orders deleted: {orders_deleted}")
        print("="*60)
        print("\n✅ Operation completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
