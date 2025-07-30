import pandas as pd
import pymongo
import os
import argparse
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from bson import ObjectId
from src.config.settings import MONGODB_URL, DB_NAME

# Custom PyObjectId class for MongoDB ObjectId validation
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        json_schema = handler(core_schema)
        json_schema.update(type="string")
        return json_schema

# Mongo salesman model
class SalesManInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=12)
    state: Optional[str] = Field(default=None, max_length=50)
    dealers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

def migrate_salesmen(mongo_uri, database_name, ods_file_path):
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongo_uri)
        db = client[database_name]
        collection = db["salesmen"]
        
        # Read the ODS file
        df = pd.read_excel(ods_file_path, engine="odf", usecols=[0], header=None)
        salesman_names = df[0].dropna().tolist()  # Get names from first column, remove NaN

        if not salesman_names:
            print("No salesman names found in the ODS file.")
            return

        # Prepare documents
        documents = []
        for name in salesman_names:
            if isinstance(name, str) and len(name.strip()) >= 3:
                try:
                    salesman = SalesManInDB(
                        name=name.strip(),
                        email="placeholder@example.com",  # Placeholder to satisfy EmailStr
                        phone=None,
                        state="WB",
                        dealers=[],
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    documents.append(salesman.dict(by_alias=True))
                except ValueError as e:
                    print(f"Skipping invalid salesman name '{name}': {str(e)}")
                    continue
            else:
                print(f"Skipping invalid or short name: '{name}'")

        if not documents:
            print("No valid salesman documents to insert.")
            return

        # Check for existing names to avoid duplicates
        existing_names = set(
            collection.find({"name": {"$in": [doc["name"] for doc in documents]}}).distinct("name")
        )
        new_documents = [doc for doc in documents if doc["name"] not in existing_names]

        if new_documents:
            result = collection.insert_many(new_documents, ordered=False)
            print(f"Successfully inserted {len(result.inserted_ids)} new salesman documents.")
        else:
            print("No new salesman documents to insert (all names already exist).")

    except Exception as e:
        print(f"Migration failed: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate salesman data from ODS file to MongoDB")
    parser.add_argument("--mongo-uri", default=MONGODB_URL, help="mongo connection uri")
    parser.add_argument("--database", default=DB_NAME, help="MongoDB database name")
    parser.add_argument("--ods-file", default="./ods.ods",
                        help="Path to the up_salesman.ods file")
    
    args = parser.parse_args()

    migrate_salesmen(args.mongo_uri, args.database, args.ods_file)
