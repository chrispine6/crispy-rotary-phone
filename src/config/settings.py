import os

MONGODB_URL = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://nexfarm_admin:nexfarm_db_password@cluster0.aicbbge.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = "nexfarm_db"
