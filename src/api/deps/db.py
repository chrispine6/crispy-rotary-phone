from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import Request

def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db
