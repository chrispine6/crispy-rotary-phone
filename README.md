Nexfarm API
A FastAPI server for the Nexfarm application with MongoDB integration.
Setup

Clone the repository:
git clone <repository-url>
cd crispy-rotary-phone


Create and activate a virtual environment:
python -m venv venv
source venv/bin/activate


Install dependencies:
pip install -r requirements.txt


Set MongoDB credentials:

Update src/config/settings.py with your MongoDB Atlas credentials or set the MONGODB_URL environment variable:export MONGODB_URL="mongodb+srv://<username>:<password>@cluster0.aicbbge.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"




Run the server:
python src/main.py


Access the API:

API docs: http://localhost:8002/docs
MongoDB connection check: http://localhost:8002/api/check-mongodb-connection



Endpoints

GET /api/check-mongodb-connection: Check MongoDB connection status.

