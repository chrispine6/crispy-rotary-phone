from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
import logging
import os
import sys

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.routes.database import router as database_router
from api.routes.order import router as order_router
from api.routes.forecasts import router as forecast_router
from config.settings import MONGODB_URL, DB_NAME
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# initialise fast api server
app = FastAPI(title="nexfarm", description="nexfarm server", version="0.1.0")

# CORS configuration - get allowed origins from environment
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
if allowed_origins == ["*"]:
    # Development mode - allow all origins
    origins = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "https://nex-grow.co.in",
        "https://www.nex-grow.co.in",
        "https://api.nex-grow.co.in",
        "*"
    ]
else:
    # Production mode - use specific origins
    origins = [origin.strip() for origin in allowed_origins]

# CORS middleware (must be before routers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],
)

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

# include router
app.include_router(database_router, prefix="/api", tags=["database"])
app.include_router(order_router, prefix="/api/orders", tags=["orders"])
app.include_router(forecast_router, prefix="/api", tags=["forecasts"])

PRIVACY_POLICY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Privacy Policy — NexGrow</title>
<style>
:root{--green:#128d3b;--green-dark:#0c6b2c;--green-tint:#e6f0e8;--bg:#f7faf9;--surface:#ffffff;--text:#1c2b1e;--text-soft:#4a6350;--text-muted:#7a9280;--border:#d4e4d8;--rule:#128d3b}
@media(prefers-color-scheme:dark){:root{--bg:#111a12;--surface:#1a2b1c;--text:#ddeee0;--text-soft:#8aac8d;--text-muted:#567060;--border:#2a402c;--green-tint:#162418;--green:#3daa66;--green-dark:#22c55e;--rule:#3daa66}}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:Georgia,'Times New Roman',Times,serif;font-size:16px;line-height:1.75;-webkit-font-smoothing:antialiased;padding:0 1rem 4rem}
.page{max-width:680px;margin:0 auto}
.doc-header{padding:2.5rem 0 2rem;border-bottom:1px solid var(--border);margin-bottom:2rem;display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:.6rem}
.brand-mark{width:32px;height:32px;background:var(--green);border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.brand-name{font-family:system-ui,-apple-system,sans-serif;font-size:1.05rem;font-weight:700;color:var(--text);letter-spacing:-.01em}
.doc-meta{font-family:system-ui,-apple-system,sans-serif;font-size:.78rem;color:var(--text-muted);text-align:right;line-height:1.5}
.doc-title{font-family:system-ui,-apple-system,sans-serif;font-size:clamp(1.5rem,4vw,2rem);font-weight:700;color:var(--text);letter-spacing:-.02em;line-height:1.2;margin-bottom:.5rem}
.doc-subtitle{font-family:system-ui,-apple-system,sans-serif;font-size:.9rem;color:var(--text-soft);margin-bottom:2rem}
.summary{background:var(--green-tint);border:1px solid var(--border);border-left:3px solid var(--rule);border-radius:6px;padding:1rem 1.25rem;margin-bottom:2.5rem}
.summary-label{font-family:system-ui,-apple-system,sans-serif;font-size:.7rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--green);margin-bottom:.6rem}
.summary-list{list-style:none;display:flex;flex-wrap:wrap;gap:.4rem}
.summary-list li{font-family:system-ui,-apple-system,sans-serif;font-size:.78rem;background:var(--surface);border:1px solid var(--border);border-radius:99px;padding:.2rem .65rem;color:var(--text-soft);line-height:1.5}
.section{margin-bottom:2.5rem;padding-left:1rem;border-left:2px solid var(--border)}
.section:hover{border-left-color:var(--rule)}
.section-title{font-family:system-ui,-apple-system,sans-serif;font-size:.95rem;font-weight:700;color:var(--text);letter-spacing:-.01em;margin-bottom:.6rem}
.section p{color:var(--text-soft);font-size:.95rem;margin-bottom:.75rem}
.section p:last-child{margin-bottom:0}
.section ul{padding-left:1.25rem;color:var(--text-soft);font-size:.95rem}
.section ul li{margin-bottom:.35rem}
.third-party{width:100%;border-collapse:collapse;font-family:system-ui,-apple-system,sans-serif;font-size:.82rem;margin-top:.75rem;overflow-x:auto;display:block}
.third-party th{text-align:left;padding:.5rem .75rem;background:var(--green-tint);color:var(--text-soft);font-weight:600;letter-spacing:.03em;border-bottom:1px solid var(--border)}
.third-party td{padding:.5rem .75rem;color:var(--text-soft);border-bottom:1px solid var(--border);vertical-align:top}
.third-party tr:last-child td{border-bottom:none}
.third-party td:first-child{font-weight:600;color:var(--text);white-space:nowrap}
.doc-footer{margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--border);font-family:system-ui,-apple-system,sans-serif;font-size:.8rem;color:var(--text-muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:.5rem}
.contact-link{color:var(--green);text-decoration:none;font-weight:500}
strong{color:var(--text);font-weight:600}
@media(max-width:480px){.doc-header{flex-direction:column;gap:.5rem}.doc-meta{text-align:left}}
</style>
</head>
<body>
<div class="page">
  <header class="doc-header">
    <div class="brand">
      <div class="brand-mark">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 2C5.5 2 3 5 3 8.5c0 2.5 1.5 4.5 3.5 5.5V15h5v-1c2-1 3.5-3 3.5-5.5C15 5 12.5 2 9 2z" fill="white" fill-opacity="0.9"/><path d="M7 15h4M9 13v2" stroke="white" stroke-width="1.2" stroke-linecap="round"/></svg>
      </div>
      <span class="brand-name">NexGrow</span>
    </div>
    <div class="doc-meta">Effective: July 10, 2026<br>Version 1.0</div>
  </header>
  <h1 class="doc-title">Privacy Policy</h1>
  <p class="doc-subtitle">How NexGrow collects, uses, and protects your information.</p>
  <div class="summary">
    <div class="summary-label">At a glance</div>
    <ul class="summary-list">
      <li>Business use only</li><li>No ads or tracking</li><li>Data not sold</li><li>Firebase Authentication</li><li>Encrypted storage</li><li>Contact admin to delete</li>
    </ul>
  </div>
  <div class="section"><h2 class="section-title">Who This Policy Applies To</h2><p>NexGrow is an internal business tool used exclusively by Nexfarm's sales teams — including salespeople, sales managers, and directors. Access is restricted to personnel authorised by Nexfarm administrators.</p></div>
  <div class="section"><h2 class="section-title">Information We Collect</h2><p>We collect only what is necessary to operate the app:</p><ul><li><strong>Account details</strong> — your name, email address, job role, and phone number</li><li><strong>Authentication data</strong> — managed by Firebase Authentication; we receive a unique identifier after sign-in</li><li><strong>Business data</strong> — orders you create or manage, sales forecasts, and customer records</li><li><strong>App activity</strong> — login timestamps and basic usage logs for operational and security purposes</li></ul><p>We do not collect location data, device contacts, camera or microphone access, or any data unrelated to your sales activity.</p></div>
  <div class="section"><h2 class="section-title">How We Use Your Information</h2><p>Your information is used solely to:</p><ul><li>Verify your identity and manage access to the app</li><li>Enable creation, tracking, and management of sales orders</li><li>Support sales forecasting and performance reporting</li><li>Allow managers and directors to view and manage their team's activity</li><li>Maintain the security and reliability of the service</li></ul><p>We do not use your data for advertising, profiling, or any purpose outside of operating NexGrow.</p></div>
  <div class="section"><h2 class="section-title">Third-Party Services</h2><p>NexGrow uses the following third-party services to function:</p><table class="third-party"><thead><tr><th>Service</th><th>Provider</th><th>Purpose</th></tr></thead><tbody><tr><td>Firebase Authentication</td><td>Google LLC</td><td>Secure user sign-in and identity management</td></tr><tr><td>MongoDB Atlas</td><td>MongoDB, Inc.</td><td>Encrypted cloud database storage</td></tr><tr><td>DigitalOcean</td><td>DigitalOcean LLC</td><td>Application server hosting</td></tr></tbody></table><p>We do not sell, rent, or share your personal information with any third party for marketing or commercial purposes.</p></div>
  <div class="section"><h2 class="section-title">Data Storage and Security</h2><p>All data is stored on MongoDB Atlas and served via DigitalOcean infrastructure. We protect your data using encrypted connections (TLS/HTTPS), encrypted storage at rest, and role-based access controls. Deactivated accounts are immediately blocked from accessing the system.</p></div>
  <div class="section"><h2 class="section-title">Data Retention</h2><p>We retain your account and associated business data for as long as your account is active and for up to 12 months following deactivation. You may request earlier deletion by contacting your administrator.</p></div>
  <div class="section"><h2 class="section-title">Your Rights</h2><p>You have the right to request a copy of your data, correction of inaccurate information, or deletion of your account. To exercise these rights, contact your Nexfarm administrator or reach us at the address below.</p></div>
  <div class="section"><h2 class="section-title">Children's Privacy</h2><p>NexGrow is a professional business application intended for adults. We do not knowingly collect information from anyone under 18 years of age.</p></div>
  <div class="section"><h2 class="section-title">Changes to This Policy</h2><p>We may update this policy as the app evolves. Material changes will be communicated through the app or by email. Continued use of NexGrow after changes are posted constitutes acceptance of the updated policy.</p></div>
  <footer class="doc-footer">
    <span>© 2026 Nexfarm. All rights reserved.</span>
    <span>Questions? <a class="contact-link" href="mailto:accounts@nex-farm.com">accounts@nex-farm.com</a></span>
  </footer>
</div>
</body>
</html>"""

@app.get("/privacy-policy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy():
    return HTMLResponse(content=PRIVACY_POLICY_HTML)

# Health check endpoint
@app.get("/")
async def root():
    return {"message": "NexFarm API is running", "status": "healthy"}

@app.get("/health")
async def health_check():
    try:
        # Test database connection
        if mongodb is not None:
            await mongodb.list_collection_names()
            db_status = "connected"
        else:
            db_status = "disconnected"
        
        return {
            "status": "healthy",
            "database": db_status,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "version": "0.1.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "error",
            "error": str(e)
        }

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
