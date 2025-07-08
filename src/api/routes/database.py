from fastapi import APIRouter, HTTPException
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from api.models.connection import ConnectionResponse
from config.settings import MONGODB_URL, DB_NAME

router = APIRouter()

@router.get("/check-mongodb-connection", response_model=ConnectionResponse)
async def check_mongodb_connection():
    try:
        client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        db.command("ping")
        client.close()
        return ConnectionResponse(
            status="success",
            message="Successfully connected to MongoDB"
        )
    except ConnectionFailure as e:
        raise HTTPException(
            status_code=500,
            detail=ConnectionResponse(
                status="error",
                message=f"Failed to connect to MongoDB: {str(e)}"
            ).dict()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ConnectionResponse(
                status="error",
                message=f"An unexpected error occurred: {str(e)}"
            ).dict()
        )
