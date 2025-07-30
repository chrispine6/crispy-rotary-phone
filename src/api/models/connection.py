from pydantic import BaseModel

class ConnectionResponse(BaseModel):
    status: str
    message: str
