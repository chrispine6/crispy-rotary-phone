from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from api.routes.database import router as database_router
from api.routes.order import router as order_router
from config.settings import MONGODB_URL, DB_NAME
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# initialise fast api server
app = FastAPI(title="nexfarm", description="nexfarm server", version="0.1.0")

# Global variable for MongoDB client and database
mongodb_client = None
mongodb = None

# Startup event to connect to MongoDB
@app.on_event("startup")
async def connect_to_mongo():
    global mongodb_client, mongodb
    mongodb_client = AsyncIOMotorClient(MONGODB_URL)
    mongodb = mongodb_client[DB_NAME]
    app.state.db = mongodb

# Shutdown event to close MongoDB connection
@app.on_event("shutdown")
async def close_mongo_connection():
    global mongodb_client
    if mongodb_client:
        mongodb_client.close()

# cors middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],\
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# include router
app.include_router(database_router, prefix="/api", tags=["database"])
app.include_router(order_router, prefix="/api/orders", tags=["orders"])

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
