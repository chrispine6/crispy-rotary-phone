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
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        json_schema = handler(core_schema)
        json_schema.update(type="string")
        return json_schema

# Mongo product model
class ProductInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=3, max_length=100)
    category: str = Field(..., min_length=3, max_length=100)
    packing_size: str = Field(..., min_length=1, max_length=50)
    bottles_per_case: int = Field(..., ge=1)
    bottle_volume: str = Field(..., min_length=1, max_length=20)
    moq: str = Field(..., min_length=1, max_length=50)
    dealer_price_per_bottle: float = Field(..., gt=0.0)
    gst_percentage: float = Field(..., ge=0.0)
    billing_price_per_bottle: float = Field(..., gt=0.0)
    mrp_per_bottle: float = Field(..., gt=0.0)
    product_details: Optional[str] = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

def parse_packing_size(packing_size: str) -> tuple[int, str]:
    """Parse packing size (e.g., '50x100 ML' or '50') into bottles_per_case and bottle_volume."""
    try:
        packing_size = packing_size.strip().replace("X", "x")
        if "x" in packing_size:
            parts = packing_size.split("x")
            if len(parts) != 2:
                raise ValueError("Invalid packing size format")
            bottles = int(parts[0].strip())
            volume = parts[1].strip()
        else:
            bottles = int(packing_size)
            volume = "unit"  # Default for non-bottle formats (e.g., bags)
        if bottles < 1:
            raise ValueError("Bottles per case must be at least 1")
        return bottles, volume
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid packing size '{packing_size}': {str(e)}")

def migrate_products(mongo_uri, database_name, ods_file_path):
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongo_uri)
        db = client[database_name]
        collection = db["products"]
        
        # Read the ODS file (no header, 8 columns)
        df = pd.read_excel(ods_file_path, engine="odf", header=None, usecols=range(8))
        # Drop rows with all NaN values
        df = df.dropna(how="all")
        if df.empty:
            print("No product data found in the ODS file.")
            return

        # Prepare documents
        documents = []
        default_category = "Miscellaneous"  # Default category since column is missing
        for _, row in df.iterrows():
            try:
                # Map columns to ProductInDB fields (8 columns: name, packing_size, moq, dealer_price, gst_amount, billing_price, mrp, product_details)
                name = str(row[0]).strip()
                packing_size = str(row[1]).strip()
                moq = str(row[2]).strip()
                dealer_price = float(row[3])
                gst_amount = float(row[4])
                billing_price = float(row[5])
                mrp = float(row[6])
                product_details = str(row[7]).strip() if pd.notna(row[7]) else None

                # Parse packing size
                bottles_per_case, bottle_volume = parse_packing_size(packing_size)

                # Validate using ProductInDB
                product = ProductInDB(
                    name=name,
                    category=default_category,
                    packing_size=packing_size,
                    bottles_per_case=bottles_per_case,
                    bottle_volume=bottle_volume,
                    moq=moq,
                    dealer_price_per_bottle=dealer_price,
                    gst_percentage=(gst_amount / dealer_price) * 100 if dealer_price > 0 else 0.0,
                    billing_price_per_bottle=billing_price,
                    mrp_per_bottle=mrp,
                    product_details=product_details,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                documents.append(product.dict(by_alias=True))
            except (ValueError, TypeError) as e:
                print(f"Skipping invalid product row '{name}' with packing size '{packing_size}': {str(e)}")
                continue

        if not documents:
            print("No valid product documents to insert.")
            return

        # Check for existing products (name + packing_size as unique identifier)
        existing_keys = set(
            tuple(doc[k] for k in ["name", "packing_size"])
            for doc in collection.find(
                {"$or": [{"name": doc["name"], "packing_size": doc["packing_size"]} for doc in documents]}
            )
        )
        new_documents = [
            doc for doc in documents
            if (doc["name"], doc["packing_size"]) not in existing_keys
        ]

        if new_documents:
            result = collection.insert_many(new_documents, ordered=False)
            print(f"Successfully inserted {len(result.inserted_ids)} new product documents.")
        else:
            print("No new product documents to insert (all products already exist).")

    except Exception as e:
        print(f"Migration failed: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate product data from ODS file to MongoDB")
    parser.add_argument("--mongo-uri", default=MONGODB_URL, help="mongo connection uri")
    parser.add_argument("--database", default=DB_NAME, help="MongoDB database name")
    parser.add_argument("--ods-file", default="./ods.ods",
                        help="Path to the ods.ods file")
    
    args = parser.parse_args()

    migrate_products(args.mongo_uri, args.database, args.ods_file)
