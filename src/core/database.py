from pymongo import MongoClient
from config.settings import MONGODB_URL, DB_NAME

def get_db():
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]
