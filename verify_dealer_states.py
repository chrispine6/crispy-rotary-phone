"""
Verification script to check dealer states after migration.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

# MongoDB connection details
MONGO_URI = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://nexfarm_admin:sgFeiUpVjWwuv84W@cluster0.aicbbge.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = "nexfarm_db"

async def verify_dealer_states():
    """Verify all dealer states are 2-letter codes."""
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DB_NAME]
        dealers_collection = db.dealers
        
        # Get all dealers
        dealers_cursor = dealers_collection.find({})
        dealers = await dealers_cursor.to_list(length=10000)
        
        print(f"\nVerifying {len(dealers)} dealers...\n")
        
        valid_count = 0
        invalid_dealers = []
        state_distribution = Counter()
        
        for dealer in dealers:
            state = dealer.get('state', '').strip()
            
            # Check if it's a valid 2-letter code
            if len(state) == 2 and state.isupper() and state.isalpha():
                valid_count += 1
                state_distribution[state] += 1
            else:
                invalid_dealers.append({
                    'name': dealer.get('name', 'Unknown'),
                    'state': state
                })
        
        print("="*60)
        print("VERIFICATION RESULTS")
        print("="*60)
        print(f"Total dealers: {len(dealers)}")
        print(f"Valid 2-letter state codes: {valid_count}")
        print(f"Invalid states: {len(invalid_dealers)}")
        
        if invalid_dealers:
            print("\n❌ Dealers with invalid states:")
            for dealer in invalid_dealers:
                print(f"  - {dealer['name']}: '{dealer['state']}'")
        else:
            print("\n✅ All dealers have valid 2-letter state codes!")
        
        print("\n" + "="*60)
        print("STATE DISTRIBUTION")
        print("="*60)
        for state, count in sorted(state_distribution.items()):
            print(f"{state}: {count} dealers")
        
        client.close()
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(verify_dealer_states())
