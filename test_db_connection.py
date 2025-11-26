# Test MongoDB connection
import os
from pymongo import MongoClient
import sys
sys.path.append('src')
from config.settings import MONGODB_URL, DB_NAME

print(f"Attempting to connect to: {MONGODB_URL}")
print(f"Database name: {DB_NAME}")

try:
    # Test connection
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    
    # Try to access the database
    db = client[DB_NAME]
    
    # Test a simple operation
    collections = db.list_collection_names()
    print(f"✅ Connection successful!")
    print(f"Available collections: {collections}")
    
    # Test authentication by trying to read from a collection
    if 'salesmen' in collections:
        count = db.salesmen.count_documents({})
        print(f"Salesmen collection has {count} documents")
    
    client.close()
    
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\nPossible solutions:")
    print("1. Check if your IP address is whitelisted in MongoDB Atlas")
    print("2. Verify the username and password are correct")
    print("3. Check if the cluster is running")
    print("4. Try using a different connection string")