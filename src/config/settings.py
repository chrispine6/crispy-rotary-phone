import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

MONGODB_URL = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://nexfarm_admin:nexfarm_db_password@cluster0.aicbbge.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = "nexfarm_db"
EMAIL_HOST="smtp.gmail.com"
EMAIL_PORT=587
EMAIL_USER="fayaqueisawesome@gmail.com"
EMAIL_PASS="qdazoxehaszonoyu"
BOSS_EMAIL="fayaque.ali22@gmail.com"
