import pandas as pd
import pymongo
import os
import argparse
from pydantic import BaseModel, Field
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
    def validate(cls, v, info):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        json_schema = handler(core_schema)
        json_schema.update(type="string")
        return json_schema

# Mongo dealer model
class DealerInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=3, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=12)
    state: Optional[str] = Field(default="UP", max_length=50)
    sales_man_id: PyObjectId
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

def migrate_dealers(mongo_uri, database_name, ods_file_path):
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongo_uri)
        db = client[database_name]
        collection = db["dealers"]
        
        # Read the ODS file
        df = pd.read_excel(ods_file_path, engine="odf", usecols=[0], header=None)
        dealer_names = df[0].dropna().tolist()  # Get names from first column, remove NaN

        if not dealer_names:
            print("No dealer names found in the ODS file.")
            return

        # Prepare documents
        documents = []
        salesman_id = PyObjectId("686d27401a54fd3dfb550a00")  # Hardcode Prashant's ObjectId
        for name in dealer_names:
            if isinstance(name, str) and len(name.strip()) >= 3:
                try:
                    dealer = DealerInDB(
                        name=name.strip(),
                        phone=None,
                        state="TG",
                        sales_man_id=salesman_id,  # Use Prashant's ObjectId
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    documents.append(dealer.model_dump(by_alias=True))
                except ValueError as e:
                    print(f"Skipping invalid dealer name '{name}': {str(e)}")
                    continue
            else:
                print(f"Skipping invalid or short name: '{name}'")

        if not documents:
            print("No valid dealer documents to insert.")
            return

        # Check for existing names to avoid duplicates
        existing_names = set(
            collection.find({"name": {"$in": [doc["name"] for doc in documents]}}).distinct("name")
        )
        new_documents = [doc for doc in documents if doc["name"] not in existing_names]

        if new_documents:
            result = collection.insert_many(new_documents, ordered=False)
            print(f"Successfully inserted {len(result.inserted_ids)} new dealer documents.")
        else:
            print("No new dealer documents to insert (all names already exist).")

    except Exception as e:
        print(f"Migration failed: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate dealer data from ODS file to MongoDB")
    parser.add_argument("--mongo-uri", default=MONGODB_URL, help="mongo connection uri")
    parser.add_argument("--database", default=DB_NAME, help="MongoDB database name")
    parser.add_argument("--ods-file", default="./ods.ods",
                        help="Path to the ods.ods file")
    
    args = parser.parse_args()

    migrate_dealers(args.mongo_uri, args.database, args.ods_file)
