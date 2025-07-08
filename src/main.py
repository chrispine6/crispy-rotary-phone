from fastapi import FastAPI
from api.routes.database import router as database_router

# initialise fast api server
app = FastAPI(title="nexfarm", description="nexfarm server", version="0.1.0")

# include router
app.include_router(database_router, prefix="/api", tags=["database"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
