"""
Migration script to convert dealer state names to 2-letter abbreviations.
This script updates all dealers in the database that have full state names
to use the standard 2-letter state codes.
"""

import pymongo
import asyncio
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

# State name to code mapping
STATE_MAPPING = {
    # States
    'andhra pradesh': 'AP',
    'arunachal pradesh': 'AR',
    'assam': 'AS',
    'bihar': 'BR',
    'chhattisgarh': 'CG',
    'goa': 'GA',
    'gujarat': 'GJ',
    'haryana': 'HR',
    'himachal pradesh': 'HP',
    'jharkhand': 'JH',
    'karnataka': 'KA',
    'kerala': 'KL',
    'madhya pradesh': 'MP',
    'maharashtra': 'MH',
    'manipur': 'MN',
    'meghalaya': 'ML',
    'mizoram': 'MZ',
    'nagaland': 'NL',
    'odisha': 'OR',
    'punjab': 'PB',
    'rajasthan': 'RJ',
    'sikkim': 'SK',
    'tamil nadu': 'TN',
    'telangana': 'TG',
    'tripura': 'TR',
    'uttar pradesh': 'UP',
    'uttarakhand': 'UT',
    'west bengal': 'WB',
    # Union Territories
    'andaman and nicobar islands': 'AN',
    'chandigarh': 'CH',
    'dadra and nagar haveli and daman and diu': 'DN',
    'delhi': 'DL',
    'jammu and kashmir': 'JK',
    'ladakh': 'LA',
    'lakshadweep': 'LD',
    'puducherry': 'PY',
    # Common variations
    'pondicherry': 'PY',
    'orissa': 'OR',
}

async def update_dealer_states():
    """Update all dealer states to 2-letter abbreviations."""
    try:
        # Connect to MongoDB
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DB_NAME]
        dealers_collection = db.dealers
        
        # Get all dealers
        dealers_cursor = dealers_collection.find({})
        dealers = await dealers_cursor.to_list(length=10000)
        
        updated_count = 0
        already_correct = 0
        not_found = []
        
        print(f"\nFound {len(dealers)} dealers to check...")
        
        for dealer in dealers:
            dealer_id = dealer.get('_id')
            current_state = dealer.get('state', '').strip()
            
            if not current_state:
                print(f"⚠️  Dealer {dealer.get('name', 'Unknown')} (ID: {dealer_id}) has no state")
                continue
            
            # Check if it's already a proper 2-letter code
            if len(current_state) == 2 and current_state.upper() == current_state and current_state.isalpha():
                already_correct += 1
                continue
            
            # Handle case where it's a 2-letter code but wrong case (e.g., "up", "Up")
            if len(current_state) == 2 and current_state.isalpha():
                new_state = current_state.upper()
                result = await dealers_collection.update_one(
                    {'_id': dealer_id},
                    {'$set': {'state': new_state}}
                )
                
                if result.modified_count > 0:
                    print(f"✓ Updated dealer '{dealer.get('name', 'Unknown')}' (ID: {dealer_id}): '{current_state}' → '{new_state}' (case fix)")
                    updated_count += 1
                continue
            
            # Convert to lowercase for lookup
            state_lower = current_state.lower()
            
            # Find the corresponding 2-letter code
            new_state = STATE_MAPPING.get(state_lower)
            
            if new_state:
                # Update the dealer
                result = await dealers_collection.update_one(
                    {'_id': dealer_id},
                    {'$set': {'state': new_state}}
                )
                
                if result.modified_count > 0:
                    print(f"✓ Updated dealer '{dealer.get('name', 'Unknown')}' (ID: {dealer_id}): '{current_state}' → '{new_state}'")
                    updated_count += 1
            else:
                # State not found in mapping
                not_found.append({
                    'name': dealer.get('name', 'Unknown'),
                    'id': str(dealer_id),
                    'state': current_state
                })
                print(f"❌ Unknown state for dealer '{dealer.get('name', 'Unknown')}' (ID: {dealer_id}): '{current_state}'")
        
        # Print summary
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Total dealers checked: {len(dealers)}")
        print(f"Already using 2-letter codes: {already_correct}")
        print(f"Successfully updated: {updated_count}")
        print(f"Unknown states: {len(not_found)}")
        
        if not_found:
            print("\nDealers with unknown states:")
            for item in not_found:
                print(f"  - {item['name']} (ID: {item['id']}): {item['state']}")
            print("\nPlease manually review and update these dealers.")
        
        print("\n✅ Migration completed!")
        
        client.close()
        
    except Exception as e:
        print(f"\n❌ Error during migration: {str(e)}")
        raise

if __name__ == "__main__":
    print("="*60)
    print("DEALER STATE MIGRATION SCRIPT")
    print("="*60)
    print("This script will convert all dealer state names to 2-letter codes.")
    print("="*60)
    
    # Run the migration
    asyncio.run(update_dealer_states())
