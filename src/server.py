# fast api server for nexfarm

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

# declare the app
app = FastAPI(title="nexfarm", description="nexfarm server", version="1.0.0")

# now define a pydantic model for request/response data
class Item(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: float

# now define routes

