# logic for making orders

from fastapi import APIRouter, Depends, HTTPException, Query, Body
router = APIRouter(tags=["orders"])

# Admin utility: clear all firebase_uid fields on salesmen and directors

from typing import List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from api.deps.db import get_db
from api.models.sales_men import SalesManInDB, SalesManSimpleResponse
from api.models.dealers import DealerInDB
from api.models.products import ProductInDB, ProductSimpleResponse, ProductPackingResponse
from api.models.orders import OrderInDB
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from bson.errors import InvalidId
from api.middleware.admin_check import admin_check
from pymongo import ReturnDocument

import smtplib
import asyncio
import threading
from email.message import EmailMessage
from config.settings import EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS, BOSS_EMAIL, EMAIL_ENABLED

router = APIRouter(tags=["orders"])

# Function to clean ObjectId fields from MongoDB documents
def clean_object_ids(obj):
    # Recursively convert ObjectId fields to strings in dicts/lists
    if isinstance(obj, dict):
        return {k: clean_object_ids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_object_ids(v) for v in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj

# Helper to resolve current user as sales manager and fetch their team salesman ids
async def _resolve_manager_team_ids(db: AsyncIOMotorDatabase, uid: str | None, email: str | None):
    try:
        # Find the salesmen doc for current user by uid/email
        user_doc = None
        if uid:
            user_doc = await db.salesmen.find_one({"firebase_uid": uid})
        if not user_doc and email:
            import re
            pattern = f"^{re.escape(email)}$"
            user_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})

        if not user_doc:
            # Try to resolve manager directly from sales_managers using email
            mgr_doc = None
            if email:
                import re
                pattern = f"^{re.escape(email)}$"
                mgr_doc = await db.sales_managers.find_one({"email": {"$regex": pattern, "$options": "i"}})
                logging.info(f"DEBUG: Found mgr_doc by email: {mgr_doc}")
                if mgr_doc:
                    ids = mgr_doc.get("salesmen_ids") or []
                    # Try to include a salesman record with same email as 'own'
                    try:
                        sm = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}}, {"_id": 1})
                        if sm and sm.get("_id"):
                            ids = list(ids) + [str(sm.get("_id"))]
                    except Exception:
                        pass
                    ids = [str(x) for x in ids if x]
                    ids = list(dict.fromkeys(ids))
                    logging.info(f"DEBUG: Direct mgr lookup returning ids: {ids}")
                    return ids
            logging.info("DEBUG: No manager found via direct lookup, returning None")
            return None

        # Find the sales_managers record by email first, fallback to phone, then name (case-insensitive)
        mgr_doc = None
        if user_doc.get("email"):
            import re
            pattern = f"^{re.escape(user_doc['email'])}$"
            mgr_doc = await db.sales_managers.find_one({"email": {"$regex": pattern, "$options": "i"}})
            logging.info(f"DEBUG: mgr_doc by email: {mgr_doc}")
        if not mgr_doc and user_doc.get("phone"):
            import re
            pattern = f"^{re.escape(str(user_doc['phone']))}$"
            mgr_doc = await db.sales_managers.find_one({"phone": {"$regex": pattern, "$options": "i"}})
            logging.info(f"DEBUG: mgr_doc by phone: {mgr_doc}")
        if not mgr_doc and user_doc.get("name"):
            import re
            pattern = f"^{re.escape(user_doc['name'])}$"
            mgr_doc = await db.sales_managers.find_one({"name": {"$regex": pattern, "$options": "i"}})
            logging.info(f"DEBUG: mgr_doc by name: {mgr_doc}")

        ids = []
        if not mgr_doc:
            # Fallback: use salesmen table where sales_manager matches current manager's name
            logging.info("DEBUG: No mgr_doc found, using fallback salesmen.sales_manager lookup")
            if user_doc.get("name"):
                import re
                pattern = f"^{re.escape(user_doc['name'])}$"
                cursor = db.salesmen.find({"sales_manager": {"$regex": pattern, "$options": "i"}}, {"_id": 1})
                rows = await cursor.to_list(length=2000)
                ids = [str(r.get("_id")) for r in rows if r.get("_id")]
                logging.info(f"DEBUG: Fallback found {len(rows)} team members: {ids}")
            else:
                ids = []
                logging.info("DEBUG: No user name for fallback lookup")
        else:
            ids = mgr_doc.get("salesmen_ids") or []
            logging.info(f"DEBUG: Using mgr_doc.salesmen_ids: {ids}")

        # Always include the manager's own salesman id
        try:
            own_id = str(user_doc.get("_id")) if user_doc.get("_id") is not None else None
            if own_id:
                ids = list(ids) + [own_id]
                logging.info(f"DEBUG: Added own_id {own_id}, ids now: {ids}")
        except Exception:
            pass

        # Normalize and de-duplicate to strings
        ids = [str(x) for x in ids if x]
        ids = list(dict.fromkeys(ids))
        logging.info(f"DEBUG: Final team_ids: {ids}")
        return ids
    except Exception:
        return None

@router.get("/manager/team/dealers")
async def get_manager_team_dealers(
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Return all dealers belonging to any salesman under the current manager's team."""
    try:
        logging.info(f"DEBUG: Fetching team dealers for uid={uid}, email={email}")
        
        # TEST MODE: For testing purposes, return ALL dealers when user is a sales manager
        # First check if user is a sales manager
        user_doc = None
        if uid:
            user_doc = await db.salesmen.find_one({"firebase_uid": uid})
        if not user_doc and email:
            import re
            pattern = f"^{re.escape(email)}$"
            user_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
        
        if user_doc and user_doc.get("role") == "sales_manager":
            logging.info(f"DEBUG: User is sales_manager, returning ALL dealers for testing")
            cursor = db.dealers.find({}, {"_id": 1, "name": 1, "sales_man_id": 1})
            dealers = await cursor.to_list(length=2000)
            out = []
            for d in dealers:
                out.append({
                    "id": str(d.get("_id")),
                    "name": d.get("name"),
                    "sales_man_id": str(d.get("sales_man_id")) if d.get("sales_man_id") is not None else None
                })
            logging.info(f"DEBUG: Returning {len(out)} dealers for sales manager")
            return out
        
        # Fallback to original logic for non-managers
        team_ids = await _resolve_manager_team_ids(db, uid, email)
        logging.info(f"DEBUG: Resolved team_ids: {team_ids}")
        if not team_ids:
            logging.info("DEBUG: No team_ids found, returning empty list")
            return []
        # Build $in with both ObjectIds and raw string ids for compatibility
        in_list = []
        for sid in team_ids:
            in_list.append(sid)
            try:
                in_list.append(ObjectId(sid))
            except Exception:
                pass
        logging.info(f"DEBUG: Using in_list for dealer query: {in_list}")
        cursor = db.dealers.find({"sales_man_id": {"$in": in_list}}, {"_id": 1, "name": 1, "sales_man_id": 1})
        dealers = await cursor.to_list(length=2000)
        logging.info(f"DEBUG: Found {len(dealers)} dealers: {dealers}")
        out = []
        for d in dealers:
            out.append({
                "id": str(d.get("_id")),
                "name": d.get("name"),
                "sales_man_id": str(d.get("sales_man_id")) if d.get("sales_man_id") is not None else None
            })
        logging.info(f"DEBUG: Returning dealers: {out}")
        return out
    except Exception as e:
        logging.error(f"Error fetching manager team dealers: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error")

# endpoint to fetch all salesman by state
@router.get("/salesmen", response_model=List[SalesManSimpleResponse])
async def get_salesmen_by_state(
    state: str = Query(..., min_length=1),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Database name: {db.name}")
    logging.info(f"Collection name: salesmen")
    logging.info(f"Searching for salesmen with state: '{state}'")
    
    # Check total documents in collection
    total_count = await db.salesmen.count_documents({})
    logging.info(f"Total salesmen in database: {total_count}")
    
    # Check documents with any state
    all_states = await db.salesmen.distinct("state")
    logging.info(f"All states in database: {all_states}")
    
    # Use case-insensitive regex for state matching and only select id and name
    salesmen_cursor = db.salesmen.find(
        {"state": {"$regex": f"^{state}$", "$options": "i"}},
        {"_id": 1, "name": 1}
    )
    salesmen = await salesmen_cursor.to_list(length=100)
    
    logging.info(f"Fetched {len(salesmen)} salesmen for state: {state}")
    logging.info(f"Salesmen data: {salesmen}")
    return salesmen

# Fetch all dealers given a salesman id
@router.get("/dealers/{salesman_id}")
async def get_dealers_by_salesman(
    salesman_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Searching for dealers with salesman_id: '{salesman_id}'")
    
    # Check if this salesman is actually a sales manager
    try:
        salesman_doc = await db.salesmen.find_one({"_id": ObjectId(salesman_id)})
        if salesman_doc and salesman_doc.get("role") == "sales_manager":
            logging.info(f"DEBUG: Salesman {salesman_id} is a sales_manager, fetching team dealers")
            
            # Find the sales_managers record to get team members
            mgr_doc = None
            if salesman_doc.get("email"):
                import re
                pattern = f"^{re.escape(salesman_doc['email'])}$"
                mgr_doc = await db.sales_managers.find_one({"email": {"$regex": pattern, "$options": "i"}})
            if not mgr_doc and salesman_doc.get("phone"):
                import re
                pattern = f"^{re.escape(str(salesman_doc['phone']))}$"
                mgr_doc = await db.sales_managers.find_one({"phone": {"$regex": pattern, "$options": "i"}})
            if not mgr_doc and salesman_doc.get("name"):
                import re
                pattern = f"^{re.escape(salesman_doc['name'])}$"
                mgr_doc = await db.sales_managers.find_one({"name": {"$regex": pattern, "$options": "i"}})
            
            team_ids = []
            if mgr_doc:
                team_ids = mgr_doc.get("salesmen_ids") or []
                logging.info(f"DEBUG: Found team_ids from sales_managers: {team_ids}")
            else:
                # Fallback: find team members via salesmen.sales_manager field
                if salesman_doc.get("name"):
                    import re
                    pattern = f"^{re.escape(salesman_doc['name'])}$"
                    cursor = db.salesmen.find({"sales_manager": {"$regex": pattern, "$options": "i"}}, {"_id": 1})
                    rows = await cursor.to_list(length=2000)
                    team_ids = [str(r.get("_id")) for r in rows if r.get("_id")]
                    logging.info(f"DEBUG: Found team_ids via fallback: {team_ids}")
            
            # Always include the manager's own id
            team_ids = list(team_ids) + [salesman_id]
            team_ids = [str(x) for x in team_ids if x]
            team_ids = list(dict.fromkeys(team_ids))  # Remove duplicates
            
            logging.info(f"DEBUG: Final team_ids for manager: {team_ids}")
            
            # Build query to get all dealers for the team
            in_list = []
            for sid in team_ids:
                in_list.append(sid)
                try:
                    in_list.append(ObjectId(sid))
                except Exception:
                    pass
            
            dealers_cursor = db.dealers.find(
                {"sales_man_id": {"$in": in_list}},
                {"_id": 1, "name": 1}
            )
            dealers = await dealers_cursor.to_list(length=2000)
            
            dealers_response = []
            for dealer in dealers:
                dealers_response.append({
                    "id": str(dealer["_id"]),
                    "name": dealer["name"]
                })
            
            logging.info(f"DEBUG: Returning {len(dealers_response)} team dealers for manager")
            return dealers_response
            
    except Exception as e:
        logging.error(f"Error checking if salesman is manager: {e}")
    
    # Regular salesman logic
    # Check total documents in dealers collection
    total_count = await db.dealers.count_documents({})
    logging.info(f"Total dealers in database: {total_count}")
    
    # Build compatibility filter to match both ObjectId and raw string stored ids
    in_list = [salesman_id]
    try:
        in_list.append(ObjectId(salesman_id))
    except Exception:
        pass
    dealers_cursor = db.dealers.find(
        {"sales_man_id": {"$in": in_list}},
        {"_id": 1, "name": 1}  # Only return id and name
    )
    dealers = await dealers_cursor.to_list(length=100)
    
    # Convert ObjectId to string for JSON serialization
    dealers_response = []
    for dealer in dealers:
        dealers_response.append({
            "id": str(dealer["_id"]),
            "name": dealer["name"]
        })
    
    logging.info(f"Fetched {len(dealers_response)} dealers for salesman_id: {salesman_id}")
    logging.info(f"Dealers data: {dealers_response}")
    return dealers_response

# Fetch all products
@router.get("/products", response_model=List[ProductSimpleResponse])
async def get_all_products(
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info("Fetching all unique product names")
    
    # Get unique product names using MongoDB distinct
    unique_names = await db.products.distinct("name")
    # For each unique name, get one document to fetch its _id (first occurrence)
    products = []
    for name in unique_names:
        doc = await db.products.find_one({"name": name}, {"_id": 1, "name": 1, "gst_percentage": 1})
        if doc:
            products.append(doc)
    
    logging.info(f"Fetched {len(products)} unique products")
    return products

# Fetch product packing information by product name
@router.get("/products/{product_name}/packing", response_model=List[ProductPackingResponse])
async def get_product_packing_by_name(
    product_name: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Fetching packing info for product_name: '{product_name}'")
    
    # Find all products with the same name
    products_cursor = db.products.find(
        {"name": product_name},
        {"_id": 1, "name": 1, "packing_size": 1, "bottles_per_case": 1, "bottle_volume": 1, "moq": 1}
    )
    products = await products_cursor.to_list(length=100)
    
    if not products:
        raise HTTPException(status_code=404, detail="No products found with that name")
    
    logging.info(f"Found {len(products)} products with name '{product_name}'")
    logging.info(f"Products packing info: {products}")
    return products

async def send_email_to_boss(subject: str, order: dict, db: AsyncIOMotorDatabase):
    # Check if email is enabled
    if not EMAIL_ENABLED:
        logging.info(f"Email sending disabled - skipping notification for order: {order.get('order_code', 'Unknown')}")
        return
        
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = BOSS_EMAIL

    # Build HTML content with enhanced formatting
    order_code = order.get('order_code', '')
    order_id = str(order.get('_id', ''))
    total = order.get('total_price', 0)
    discounted_total = order.get('discounted_total', 0)
    discount = order.get('discount', 0)
    status = order.get('status', '')
    state = order.get('state', '')
    products = order.get('products', [])
    
    # Fetch dealer name
    dealer_name = "Unknown Dealer"
    dealer_id = order.get('dealer_id')
    if dealer_id:
        try:
            if len(str(dealer_id)) == 24:
                dealer_doc = await db.dealers.find_one({"_id": ObjectId(dealer_id)})
            else:
                dealer_doc = await db.dealers.find_one({"_id": dealer_id})
            if dealer_doc:
                dealer_name = dealer_doc.get('name', 'Unknown Dealer')
        except Exception as e:
            logging.error(f"Error fetching dealer name: {e}")
    
    # Fetch salesman name
    salesman_name = "Unknown Salesman"
    salesman_id = order.get('salesman_id')
    if salesman_id:
        try:
            if len(str(salesman_id)) == 24:
                salesman_doc = await db.salesmen.find_one({"_id": ObjectId(salesman_id)})
            else:
                salesman_doc = await db.salesmen.find_one({"_id": salesman_id})
            if salesman_doc:
                salesman_name = salesman_doc.get('name', 'Unknown Salesman')
        except Exception as e:
            logging.error(f"Error fetching salesman name: {e}")

    product_rows = ""
    for p in products:
        product_rows += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd;">{p.get('product_name', '')}</td>
            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{p.get('quantity', '')}</td>
            <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">₹{p.get('price', 0):,.2f}</td>
            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{p.get('discount_pct', 0)}%</td>
            <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">₹{p.get('discounted_price', 0):,.2f}</td>
        </tr>
        """

    # Create approval link
    approval_link = f"https://nexgrow-server-nu.vercel.app/admin/orders"

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #16a34a, #15803d); color: white; padding: 20px; border-radius: 8px; margin-bottom: 25px; }}
            .header h2 {{ margin: 0; font-size: 24px; }}
            .order-info {{ background-color: #f8f9fa; padding: 20px; border-radius: 6px; margin-bottom: 20px; }}
            .order-info p {{ margin: 8px 0; font-size: 16px; }}
            .label {{ font-weight: bold; color: #333; }}
            .value {{ color: #666; }}
            .products-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .products-table th {{ background-color: #16a34a; color: white; padding: 12px; text-align: left; }}
            .products-table td {{ padding: 8px; border: 1px solid #ddd; }}
            .products-table tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .approval-section {{ background-color: #e7f3ff; padding: 20px; border-radius: 6px; margin-top: 25px; text-align: center; }}
            .approval-btn {{ display: inline-block; background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 10px; }}
            .approval-btn:hover {{ background-color: #15803d; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 14px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🛒 New Order Awaiting Approval</h2>
            </div>
            
            <div class="order-info">
                <p><span class="label">Order Code:</span> <span class="value">{order_code}</span></p>
                <p><span class="label">Dealer:</span> <span class="value">{dealer_name}</span></p>
                <p><span class="label">Salesman:</span> <span class="value">{salesman_name}</span></p>
                <p><span class="label">State:</span> <span class="value">{state}</span></p>
                <p><span class="label">Status:</span> <span class="value" style="color: #f59e0b; font-weight: bold;">{status}</span></p>
                <p><span class="label">Total Price:</span> <span class="value">₹{total:,.2f}</span></p>
                <p><span class="label">Discounted Total:</span> <span class="value" style="color: #16a34a; font-weight: bold;">₹{discounted_total:,.2f} ({discount:.1f}% discount)</span></p>
            </div>

            <h3 style="color: #333; margin-bottom: 15px;">📦 Order Details</h3>
            <table class="products-table">
                <thead>
                    <tr>
                        <th>Product</th>
                        <th>Quantity</th>
                        <th>Base Price</th>
                        <th>Discount %</th>
                        <th>Final Price</th>
                    </tr>
                </thead>
                <tbody>
                    {product_rows}
                </tbody>
            </table>

            <div class="approval-section">
                <h3 style="margin-top: 0; color: #333;">⚡ Quick Actions</h3>
                <p style="margin-bottom: 20px;">Click below to review and approve this order:</p>
                <a href="{approval_link}" class="approval-btn">🔍 Review & Approve Order</a>
            </div>

            <div class="footer">
                <p>This is an automated notification from NexFarm Order Management System.</p>
                <p>Order ID: {order_id}</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email in a separate thread to avoid blocking
    def send_email_sync():
        try:
            msg.set_content("A new order has been registered. Please view in HTML format for details.")
            msg.add_alternative(html, subtype='html')

            # Set a timeout for SMTP operations
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.send_message(msg)
            logging.info("Email sent to boss successfully.")
        except OSError as e:
            if "Network is unreachable" in str(e):
                logging.error(f"Network error sending email - SMTP server unreachable: {e}")
            else:
                logging.error(f"Network/connection error sending email: {e}")
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
    
    # Run email sending in background thread
    try:
        thread = threading.Thread(target=send_email_sync, daemon=True)
        thread.start()
        logging.info(f"Email sending started in background for order: {order_code}")
    except Exception as e:
        logging.error(f"Failed to start email thread: {e}")

async def send_order_confirmation_email(subject: str, order: dict, db: AsyncIOMotorDatabase):
    # Check if email is enabled
    if not EMAIL_ENABLED:
        logging.info(f"Email sending disabled - skipping confirmation for order: {order.get('order_code', 'Unknown')}")
        return
        
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = BOSS_EMAIL

    # Build HTML content for order confirmation (no approval needed)
    order_code = order.get('order_code', '')
    order_id = str(order.get('_id', ''))
    total = order.get('total_price', 0)
    discounted_total = order.get('discounted_total', 0)
    discount = order.get('discount', 0)
    status = order.get('status', '')
    state = order.get('state', '')
    products = order.get('products', [])
    
    # Fetch dealer name
    dealer_name = "Unknown Dealer"
    dealer_id = order.get('dealer_id')
    if dealer_id:
        try:
            if len(str(dealer_id)) == 24:
                dealer_doc = await db.dealers.find_one({"_id": ObjectId(dealer_id)}, {"name": 1})
            else:
                dealer_doc = await db.dealers.find_one({"_id": dealer_id}, {"name": 1})
            if dealer_doc:
                dealer_name = dealer_doc.get('name', dealer_name)
        except Exception as e:
            logging.error(f"Error fetching dealer name: {e}")
    
    # Fetch salesman name
    salesman_name = "Unknown Salesman"
    salesman_id = order.get('salesman_id')
    if salesman_id:
        try:
            if len(str(salesman_id)) == 24:
                salesman_doc = await db.salesmen.find_one({"_id": ObjectId(salesman_id)}, {"name": 1})
            else:
                salesman_doc = await db.salesmen.find_one({"_id": salesman_id}, {"name": 1})
            if salesman_doc:
                salesman_name = salesman_doc.get('name', salesman_name)
        except Exception as e:
            logging.error(f"Error fetching salesman name: {e}")
    
    # Ensure product names are populated
    for product in products:
        if not product.get('product_name'):
            product_id = product.get('product_id')
            if product_id:
                try:
                    if len(str(product_id)) == 24:
                        product_doc = await db.products.find_one({"_id": ObjectId(product_id)}, {"name": 1})
                    else:
                        product_doc = await db.products.find_one({"_id": product_id}, {"name": 1})
                    if product_doc:
                        product['product_name'] = product_doc.get('name', 'Unknown Product')
                except Exception as e:
                    logging.error(f"Error fetching product name: {e}")
                    product['product_name'] = 'Unknown Product'

    product_rows = ""
    for p in products:
        discount_pct = p.get('discount_pct', 0)
        discounted_price = p.get('discounted_price', p.get('price', 0))
        product_rows += f"""
        <tr>
            <td>{p.get('product_name', 'Unknown Product')}</td>
            <td>{p.get('quantity', 0)}</td>
            <td>₹{p.get('price', 0):,.2f}</td>
            <td>₹{discounted_price:,.2f}</td>
        </tr>
        """
    
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color:#27AE60; border-bottom: 2px solid #27AE60; padding-bottom: 10px;">✅ Order Confirmed</h2>
            
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><b>📋 Order Code:</b> <span style="color: #27AE60; font-weight: bold;">{order_code}</span></p>
                <p><b>🏢 Dealer:</b> {dealer_name}</p>
                <p><b>👤 Salesman:</b> {salesman_name}</p>
                <p><b>📍 State:</b> {state}</p>
                <p><b>📊 Status:</b> <span style="color: #27AE60; font-weight: bold;">{status.upper()}</span></p>
            </div>
            
            <div style="background-color: #e8f5e8; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><b>💰 Total Price:</b> ₹{total:,.2f}</p>
            </div>
            
            <h3 style="color: #27AE60;">📦 Products Ordered</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width: 100%; margin: 10px 0;">
                <tr style="background-color:#D5DBDB; font-weight: bold;">
                    <th style="text-align: left;">Product Name</th>
                    <th style="text-align: center;">Qty</th>
                    <th style="text-align: right;">Price</th>
                    <th style="text-align: right;">Final Price</th>
                </tr>
                {product_rows}
            </table>
            
            <div style="text-align: center; margin: 30px 0; padding: 20px; background-color: #d4edda; border-radius: 5px;">
                <h3 style="color: #155724; margin-bottom: 15px;">📋 Order Information</h3>
                <p style="margin-bottom: 15px; color: #155724;">
                    This order has been successfully placed and is being processed.
                </p>
                <p style="font-size: 12px; color: #155724;">
                    <em>No approval required - Standard pricing applied.</em>
                </p>
            </div>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                <p><b>Order ID:</b> {order_id}</p>
                <p><b>Timestamp:</b> {order.get('created_at', 'N/A')}</p>
            </div>
        </div>
    </body>
    </html>
    """

    msg.set_content("A new order has been registered. Please view in HTML format for details.")
    msg.add_alternative(html, subtype='html')

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        logging.info("Order confirmation email sent successfully.")
        print("Order confirmation email sent.")
    except Exception as e:
        logging.error(f"Failed to send order confirmation email: {e}")
        print(f"Failed to send order confirmation email: {e}")

# Create an order document with order validation middleware
@router.post("/make-order", response_model=OrderInDB)
async def create_order(
    order: OrderInDB,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    import traceback
    try:
        logging.info(f"Received order data: {order.dict()}")
        order_dict = order.dict(by_alias=True)
        # --- NEW LOGIC: normalize per-product discounts ---
        products = order_dict.get("products", []) or []
        sum_base = 0.0
        sum_discounted = 0.0
        any_discount = False
        normalized_products = []
        for p in products:
            base = float(p.get("price") or 0)
            pct = p.get("discount_pct")
            discounted_line = p.get("discounted_price")
            # Derive pct from discounted price if missing
            if (pct is None or pct == "") and discounted_line not in (None, "") and base > 0:
                try:
                    discounted_line_val = float(discounted_line)
                    pct = ((base - discounted_line_val) / base) * 100.0
                except Exception:
                    pct = 0
            # Default pct
            if pct in (None, ""):
                pct = 0
            try:
                pct = float(pct)
            except Exception:
                pct = 0
            # Clamp pct 0-30
            if pct < 0: pct = 0
            if pct > 30: pct = 30
            # Derive discounted_line if missing
            if discounted_line in (None, ""):
                discounted_line = base - (base * pct / 100.0)
            try:
                discounted_line = float(discounted_line)
            except Exception:
                discounted_line = base
            line_discount_amt = base - discounted_line
            if line_discount_amt > 0.0000001:
                any_discount = True
            sum_base += base
            sum_discounted += discounted_line
            # Store exact (unrounded) values
            p["discount_pct"] = pct  # no rounding
            p["discounted_price"] = discounted_line  # no rounding
            normalized_products.append(p)
        order_dict["products"] = normalized_products
        order_dict["total_price"] = sum_base
        if sum_base > 0:
            order_dict["discounted_total"] = sum_discounted
            aggregate_pct = ((sum_base - sum_discounted) / sum_base) * 100.0
            order_dict["discount"] = aggregate_pct
        else:
            order_dict.setdefault("discounted_total", 0)
            order_dict.setdefault("discount", 0)
        # Derive discount_status if not provided or inconsistent
        if any_discount and order_dict.get("discount_status") in (None, "", "approved"):
            order_dict["discount_status"] = "pending"
        if not any_discount:
            order_dict["discount_status"] = "approved"
        # --- END NEW LOGIC ---
        from datetime import datetime
        now = datetime.utcnow()
        order_dict.setdefault("created_at", now)
        order_dict["updated_at"] = now
        order_dict.setdefault("status", "pending")
        # --- ORDER CODE LOGIC (FIXED) ---
        try:
            state_raw = (order_dict.get("state") or "").strip().lower() or "na"
            logging.info(f"DEBUG: Generating order code for state: {state_raw}")
            
            # Determine fiscal year (Apr 1 - Mar 31)
            if now.month < 4:
                start_year = now.year - 1
            else:
                start_year = now.year
            end_year = start_year + 1
            fiscal_year_str = f"fy{start_year}-{str(end_year)[-2:]}"  # e.g. fy2025-26
            logging.info(f"DEBUG: Fiscal year: {fiscal_year_str}")
            
            # Atomic counter per FY+state. Sequence goes from 0000 to 9999
            logging.info(f"DEBUG: Updating counter for fiscal_year={fiscal_year_str}, state={state_raw}")
            counter_doc = await db.order_counters.find_one_and_update(
                {"fiscal_year": fiscal_year_str, "state": state_raw},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
            logging.info(f"DEBUG: Counter doc result: {counter_doc}")
            
            seq_val = counter_doc.get("seq", 1)
            # seq_val starts at 1 for first order -> produce 0000, then 0001, 0002, etc.
            code_tail = f"{seq_val-1:04d}"  # 4-digit zero-padded starting from 0000
            order_code = f"nxg-{fiscal_year_str}-{state_raw}-{code_tail}"
            order_dict["order_code"] = order_code
            logging.info(f"DEBUG: Generated order code: {order_code}")
        except Exception as gen_ex:
            logging.error(f"Order code generation failed: {gen_ex}")
            import traceback
            logging.error(f"Full traceback: {traceback.format_exc()}")
            # Fail order creation if order_code cannot be generated to ensure data integrity
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to generate order code due to database connectivity issues. Please try again later."
            )
        # --- END ORDER CODE LOGIC ---
        # Ensure '_id' is not set for new orders
        order_dict.pop("_id", None)
        result = await db.orders.insert_one(order_dict)
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Order creation failed")
        order_dict["_id"] = result.inserted_id

        # Send email to boss after successful order registration (non-blocking)
        subject = f"New Order Registered: {order_dict.get('order_code', '')}"
        try:
            await send_email_to_boss(subject, order_dict, db)
        except Exception as e:
            logging.error(f"Email sending failed but order was created successfully: {e}")

        return order_dict
    except RequestValidationError as e:
        logging.error(f"Validation error while creating order: {e.errors()}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error while creating order: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Fetch product price by product id and quantity
@router.get("/products/{product_id}/price")
async def get_product_price(
    product_id: str,
    quantity: int = Query(..., gt=0),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    logging.info(f"Fetching price for product_id: '{product_id}' with quantity: {quantity}")
    product = await db.products.find_one(
        {"_id": ObjectId(product_id)},
        {"dealer_price_per_bottle": 1, "billing_price_per_bottle": 1, "mrp_per_bottle": 1, "name": 1, "bottles_per_case": 1}
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    price_per_bottle = product.get("billing_price_per_bottle") or product.get("dealer_price_per_bottle") or product.get("mrp_per_bottle")
    bottles_per_case = product.get("bottles_per_case", 1)
    if price_per_bottle is None:
        raise HTTPException(status_code=400, detail="Product price not available")
    total_price = price_per_bottle * quantity * bottles_per_case
    logging.info(f"Product: {product.get('name')}, Unit price: {price_per_bottle}, Quantity: {quantity}, Bottles/case: {bottles_per_case}, Total price: {total_price}")
    return {
        "product_id": str(product_id),
        "product_name": product.get("name"),
        "unit_price": price_per_bottle,
        "quantity": quantity,
        "bottles_per_case": bottles_per_case,
        "total_price": total_price
    }

# List all orders
@router.get("")
async def list_all_orders(
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        logging.info("Fetching all orders")
        orders_cursor = db.orders.find({})
        orders = await orders_cursor.to_list(length=1000)
        logging.info(f"Fetched {len(orders)} orders")
        cleaned_orders = []
        for order in orders:
            # Convert _id
            if "_id" in order and order["_id"] is not None:
                order["id"] = str(order["_id"])
                order["_id"] = str(order["_id"])
            # Retrieve salesman_id and fetch name
            sid = order.get("salesman_id")
            sid_str = str(sid) if sid else ""
            order["salesman_id"] = sid_str
            salesman_name = ""
            salesman_doc = None
            logging.info(f"Looking up salesman name for id: {sid_str}")
            if sid_str:
                # Try ObjectId lookup
                if len(sid_str) == 24:
                    try:
                        salesman_doc = await db.salesmen.find_one({"_id": ObjectId(sid_str)})
                        logging.info(f"Salesman lookup by ObjectId result: {salesman_doc}")
                    except Exception as ex:
                        logging.error(f"Salesman ObjectId lookup failed: {ex}")
                        salesman_doc = None
                # Try string id lookup as fallback
                if not salesman_doc:
                    salesman_doc = await db.salesmen.find_one({"_id": sid_str})
                    logging.info(f"Salesman lookup by string id result: {salesman_doc}")
                salesman_name = salesman_doc["name"] if salesman_doc and "name" in salesman_doc else ""
            order["salesman_name"] = salesman_name
            # Retrieve dealer_id and fetch name
            did = order.get("dealer_id")
            did_str = str(did) if did else ""
            order["dealer_id"] = did_str
            dealer_name = ""
            dealer_doc = None
            logging.info(f"Looking up dealer name for id: {did_str}")
            if did_str:
                # Try ObjectId lookup
                if len(did_str) == 24:
                    try:
                        dealer_doc = await db.dealers.find_one({"_id": ObjectId(did_str)})
                        logging.info(f"Dealer lookup by ObjectId result: {dealer_doc}")
                    except Exception as ex:
                        logging.error(f"Dealer ObjectId lookup failed: {ex}")
                        dealer_doc = None
                # Try string id lookup as fallback
                if not dealer_doc:
                    dealer_doc = await db.dealers.find_one({"_id": did_str})
                    logging.info(f"Dealer lookup by string id result: {dealer_doc}")
                dealer_name = dealer_doc["name"] if dealer_doc and "name" in dealer_doc else ""
            order["dealer_name"] = dealer_name
            # Retrieve products and fetch product names
            products = order.get("products", [])
            # Handle old format: single product fields
            if not products and "product_id" in order and order["product_id"] is not None:
                pid = str(order["product_id"])
                product_entry = {
                    "product_id": pid,
                    "quantity": order.get("quantity"),
                    "price": order.get("price"),
                    "product_name": None
                }
                try:
                    product_doc = await db.products.find_one({"_id": ObjectId(pid)})
                    product_entry["product_name"] = product_doc["name"] if product_doc else ""
                except Exception:
                    product_entry["product_name"] = ""
                products = [product_entry]
                order.pop("product_id", None)
                order.pop("quantity", None)
                order.pop("price", None)
                order.pop("product_name", None)
            # For each product, fetch name
            for p in products:
                pid = p.get("product_id")
                pid_str = str(pid) if pid else ""
                p["product_id"] = pid_str
                product_doc = None
                logging.info(f"Looking up product name for id: {pid_str}")
                if not p.get("product_name"):
                    # Only try ObjectId lookup if valid
                    if len(pid_str) == 24:
                        try:
                            product_doc = await db.products.find_one({"_id": ObjectId(pid_str)}, {"name": 1})
                            logging.info(f"Product lookup by ObjectId result: {product_doc}")
                        except Exception as ex:
                            logging.error(f"Product ObjectId lookup failed: {ex}")
                            product_doc = None
                    if not product_doc:
                        # Try string id lookup as fallback
                        product_doc = await db.products.find_one({"_id": pid_str}, {"name": 1})
                        logging.info(f"Product lookup by string id result: {product_doc}")
                    p["product_name"] = product_doc["name"] if product_doc and "name" in product_doc else ""
            order["products"] = products
            # Remove any remaining ObjectId fields
            for k, v in list(order.items()):
                if isinstance(v, ObjectId):
                    order[k] = str(v)
            cleaned_orders.append(order)
        logging.info(f"Returning orders: {cleaned_orders}")
        return cleaned_orders
    except Exception as e:
        logging.error(f"Error fetching orders: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Get all orders (admin only)
@router.get("/admin/orders")
async def get_all_orders_admin(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        logging.info("Fetching all orders for admin")
        orders_cursor = db.orders.find({})
        orders = await orders_cursor.to_list(length=1000)
        logging.info(f"Fetched {len(orders)} orders for admin")
        cleaned_orders = []
        for order in orders:
            # Convert _id
            if "_id" in order and order["_id"] is not None:
                order["id"] = str(order["_id"])
                order["_id"] = str(order["_id"])
            # Retrieve salesman_id and fetch name
            sid = order.get("salesman_id")
            sid_str = str(sid) if sid else ""
            order["salesman_id"] = sid_str
            salesman_name = ""
            salesman_doc = None
            logging.info(f"Looking up salesman name for id: {sid_str}")
            if sid_str:
                # Try ObjectId lookup
                if len(sid_str) == 24:
                    try:
                        salesman_doc = await db.salesmen.find_one({"_id": ObjectId(sid_str)})
                        logging.info(f"Salesman lookup by ObjectId result: {salesman_doc}")
                    except Exception as ex:
                        logging.error(f"Salesman ObjectId lookup failed: {ex}")
                        salesman_doc = None
                # Try string id lookup as fallback
                if not salesman_doc:
                    salesman_doc = await db.salesmen.find_one({"_id": sid_str})
                    logging.info(f"Salesman lookup by string id result: {salesman_doc}")
                salesman_name = salesman_doc["name"] if salesman_doc and "name" in salesman_doc else ""
            order["salesman_name"] = salesman_name
            # Retrieve dealer_id and fetch name
            did = order.get("dealer_id")
            did_str = str(did) if did else ""
            order["dealer_id"] = did_str
            dealer_name = ""
            dealer_doc = None
            logging.info(f"Looking up dealer name for id: {did_str}")
            if did_str:
                # Try ObjectId lookup
                if len(did_str) == 24:
                    try:
                        dealer_doc = await db.dealers.find_one({"_id": ObjectId(did_str)})
                        logging.info(f"Dealer lookup by ObjectId result: {dealer_doc}")
                    except Exception as ex:
                        logging.error(f"Dealer ObjectId lookup failed: {ex}")
                        dealer_doc = None
                # Try string id lookup as fallback
                if not dealer_doc:
                    dealer_doc = await db.dealers.find_one({"_id": did_str})
                    logging.info(f"Dealer lookup by string id result: {dealer_doc}")
                dealer_name = dealer_doc["name"] if dealer_doc and "name" in dealer_doc else ""
            order["dealer_name"] = dealer_name
            # Retrieve products and fetch product names
            products = order.get("products", [])
            # Handle old format: single product fields
            if not products and "product_id" in order and order["product_id"] is not None:
                pid = str(order["product_id"])
                product_entry = {
                    "product_id": pid,
                    "quantity": order.get("quantity"),
                    "price": order.get("price"),
                    "product_name": None
                }
                try:
                    product_doc = await db.products.find_one({"_id": ObjectId(pid)})
                    product_entry["product_name"] = product_doc["name"] if product_doc else ""
                except Exception:
                    product_entry["product_name"] = ""
                products = [product_entry]
                order.pop("product_id", None)
                order.pop("quantity", None)
                order.pop("price", None)
                order.pop("product_name", None)
            # For each product, fetch name
            for p in products:
                pid = p.get("product_id")
                pid_str = str(pid) if pid else ""
                p["product_id"] = pid_str
                product_doc = None
                logging.info(f"Looking up product name for id: {pid_str}")
                if not p.get("product_name"):
                    # Only try ObjectId lookup if valid
                    if len(pid_str) == 24:
                        try:
                            product_doc = await db.products.find_one({"_id": ObjectId(pid_str)}, {"name": 1})
                            logging.info(f"Product lookup by ObjectId result: {product_doc}")
                        except Exception as ex:
                            logging.error(f"Product ObjectId lookup failed: {ex}")
                            product_doc = None
                    if not product_doc:
                        # Try string id lookup as fallback
                        product_doc = await db.products.find_one({"_id": pid_str}, {"name": 1})
                        logging.info(f"Product lookup by string id result: {product_doc}")
                    p["product_name"] = product_doc["name"] if product_doc and "name" in product_doc else ""
            order["products"] = products
            # Remove any remaining ObjectId fields
            order = clean_object_ids(order)
            cleaned_orders.append(order)
        logging.info(f"Returning orders for admin: {cleaned_orders}")
        return cleaned_orders
    except Exception as e:
        logging.error(f"Error fetching orders for admin: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/admin/discount-approvals")
async def get_discount_approvals(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """List all orders with pending discount approval."""
    orders_cursor = db.orders.find({"discount_status": "pending"})
    orders = await orders_cursor.to_list(length=1000)
    
    # Enrich orders with product GST information
    enriched_orders = []
    for order in orders:
        # Normalize products and attach product names and GST percentages
        products = order.get("products", [])
        if not products and "product_id" in order and order["product_id"] is not None:
            pid = str(order["product_id"])
            product_entry = {
                "product_id": pid,
                "quantity": order.get("quantity"),
                "price": order.get("price"),
                "product_name": None
            }
            try:
                product_doc = await db.products.find_one({"_id": ObjectId(pid)})
                product_entry["product_name"] = product_doc["name"] if product_doc else ""
                product_entry["gst_percentage"] = product_doc["gst_percentage"] if product_doc else 0
            except Exception:
                product_entry["product_name"] = ""
                product_entry["gst_percentage"] = 0
            products = [product_entry]
            order.pop("product_id", None)
            order.pop("quantity", None)
            order.pop("price", None)
            order.pop("product_name", None)
        
        for p in products:
            pid = p.get("product_id")
            pid_str = str(pid) if pid else ""
            p["product_id"] = pid_str
            product_doc = None
            if not p.get("product_name"):
                if len(pid_str) == 24:
                    try:
                        product_doc = await db.products.find_one({"_id": ObjectId(pid_str)}, {"name": 1, "gst_percentage": 1})
                    except Exception:
                        product_doc = None
                if not product_doc:
                    product_doc = await db.products.find_one({"_id": pid_str}, {"name": 1, "gst_percentage": 1})
                p["product_name"] = product_doc["name"] if product_doc and "name" in product_doc else ""
                p["gst_percentage"] = product_doc["gst_percentage"] if product_doc and "gst_percentage" in product_doc else 0
        
        order["products"] = products
        # Clean ObjectId fields before returning
        enriched_orders.append(clean_object_ids(order))
    
    return enriched_orders

@router.post("/admin/approve-discount/{order_id}")
async def approve_discount(
    order_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Approve discount for an order."""
    result = await db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"discount_status": "approved"}}
    )
    if result.modified_count == 1:
        return {"success": True, "message": "Discount approved"}
    raise HTTPException(status_code=404, detail="Order not found")

@router.post("/admin/reject-discount/{order_id}")
async def reject_discount(
    order_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Reject discount for an order."""
    result = await db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"discount_status": "rejected"}}
    )
    if result.modified_count == 1:
        return {"success": True, "message": "Discount rejected"}
    raise HTTPException(status_code=404, detail="Order not found")

# Admin Salesmen Management
@router.get("/admin/salesmen")
async def get_all_salesmen(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Get all salesmen (admin only)."""
    try:
        salesmen_cursor = db.salesmen.find({})
        salesmen = await salesmen_cursor.to_list(length=1000)
        cleaned_salesmen = [clean_object_ids(salesman) for salesman in salesmen]
        return cleaned_salesmen
    except Exception as e:
        logging.error(f"Error fetching salesmen: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post("/admin/salesmen")
async def create_salesman(
    salesman_data: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Create a new salesman (admin only)."""
    try:
        from datetime import datetime
        salesman_data["created_at"] = datetime.utcnow()
        salesman_data["updated_at"] = datetime.utcnow()
        if "dealers" not in salesman_data:
            salesman_data["dealers"] = []
        # Role support: default salesman; bridge legacy 'admin' flag
        role = salesman_data.get("role")
        if role not in ("admin", "sales_manager", "salesman"):
            role = "salesman"
        salesman_data["role"] = role
        # Keep admin boolean for older UI/filters
        salesman_data["admin"] = True if role == "admin" else bool(salesman_data.get("admin", False))
        
        result = await db.salesmen.insert_one(salesman_data)
        created_salesman = await db.salesmen.find_one({"_id": result.inserted_id})
        return clean_object_ids(created_salesman)
    except Exception as e:
        logging.error(f"Error creating salesman: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.put("/admin/salesmen/{salesman_id}")
async def update_salesman(
    salesman_id: str,
    salesman_data: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Update a salesman (admin only)."""
    try:
        from datetime import datetime
        salesman_data["updated_at"] = datetime.utcnow()
        # Role support on update
        role = salesman_data.get("role")
        if role in ("admin", "sales_manager", "salesman"):
            salesman_data["admin"] = True if role == "admin" else False
        
        result = await db.salesmen.update_one(
            {"_id": ObjectId(salesman_id)},
            {"$set": salesman_data}
        )
        if result.modified_count == 1:
            updated_salesman = await db.salesmen.find_one({"_id": ObjectId(salesman_id)})
            return clean_object_ids(updated_salesman)
        raise HTTPException(status_code=404, detail="Salesman not found")
    except Exception as e:
        logging.error(f"Error updating salesman: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.delete("/admin/salesmen/{salesman_id}")
async def delete_salesman(
    salesman_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Delete a salesman (admin only)."""
    try:
        result = await db.salesmen.delete_one({"_id": ObjectId(salesman_id)})
        if result.deleted_count == 1:
            return {"success": True, "message": "Salesman deleted successfully"}
        raise HTTPException(status_code=404, detail="Salesman not found")
    except Exception as e:
        logging.error(f"Error deleting salesman: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Admin Dealers Management
@router.get("/admin/dealers")
async def get_all_dealers(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Get all dealers (admin only)."""
    try:
        dealers_cursor = db.dealers.find({})
        dealers = await dealers_cursor.to_list(length=1000)
        cleaned_dealers = [clean_object_ids(dealer) for dealer in dealers]
        return cleaned_dealers
    except Exception as e:
        logging.error(f"Error fetching dealers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post("/admin/dealers")
async def create_dealer(
    dealer_data: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Create a new dealer (admin only)."""
    try:
        from datetime import datetime
        dealer_data["created_at"] = datetime.utcnow()
        dealer_data["updated_at"] = datetime.utcnow()
        if "credit_limit" not in dealer_data:
            dealer_data["credit_limit"] = 100000
        
        # Convert sales_man_id to ObjectId if it's a string
        if "sales_man_id" in dealer_data and isinstance(dealer_data["sales_man_id"], str):
            dealer_data["sales_man_id"] = ObjectId(dealer_data["sales_man_id"])
        
        result = await db.dealers.insert_one(dealer_data)
        created_dealer = await db.dealers.find_one({"_id": result.inserted_id})
        return clean_object_ids(created_dealer)
    except Exception as e:
        logging.error(f"Error creating dealer: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.put("/admin/dealers/{dealer_id}")
async def update_dealer(
    dealer_id: str,
    dealer_data: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Update a dealer (admin only)."""
    try:
        from datetime import datetime
        dealer_data["updated_at"] = datetime.utcnow()
        
        # Convert sales_man_id to ObjectId if it's a string
        if "sales_man_id" in dealer_data and isinstance(dealer_data["sales_man_id"], str):
            dealer_data["sales_man_id"] = ObjectId(dealer_data["sales_man_id"])
        
        result = await db.dealers.update_one(
            {"_id": ObjectId(dealer_id)},
            {"$set": dealer_data}
        )
        if result.modified_count == 1:
            updated_dealer = await db.dealers.find_one({"_id": ObjectId(dealer_id)})
            return clean_object_ids(updated_dealer)
        raise HTTPException(status_code=404, detail="Dealer not found")
    except Exception as e:
        logging.error(f"Error updating dealer: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.delete("/admin/dealers/{dealer_id}")
async def delete_dealer(
    dealer_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Delete a dealer (admin only)."""
    try:
        result = await db.dealers.delete_one({"_id": ObjectId(dealer_id)})
        if result.deleted_count == 1:
            return {"success": True, "message": "Dealer deleted successfully"}
        raise HTTPException(status_code=404, detail="Dealer not found")
    except Exception as e:
        logging.error(f"Error deleting dealer: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Admin Products Management
@router.get("/admin/products")
async def get_all_products_admin(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Get all products (admin only)."""
    try:
        products_cursor = db.products.find({})
        products = await products_cursor.to_list(length=1000)
        cleaned_products = [clean_object_ids(product) for product in products]
        return cleaned_products
    except Exception as e:
        logging.error(f"Error fetching products: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post("/admin/products")
async def create_product(
    product_data: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Create a new product (admin only)."""
    try:
        from datetime import datetime
        product_data["created_at"] = datetime.utcnow()
        
        result = await db.products.insert_one(product_data)
        created_product = await db.products.find_one({"_id": result.inserted_id})
        return clean_object_ids(created_product)
    except Exception as e:
        logging.error(f"Error creating product: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.put("/admin/products/{product_id}")
async def update_product(
    product_id: str,
    product_data: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Update a product (admin only)."""
    try:
        logging.info(f"Updating product {product_id} with data: {product_data}")
        
        # Validate ObjectId format
        try:
            ObjectId(product_id)
        except Exception as id_error:
            logging.error(f"Invalid ObjectId format: {product_id}")
            raise HTTPException(status_code=400, detail="Invalid product ID format")
        
        # Remove any _id field from update data to prevent conflicts
        update_data = {k: v for k, v in product_data.items() if k != '_id'}
        
        result = await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_data}
        )
        
        logging.info(f"Update result: matched={result.matched_count}, modified={result.modified_count}")
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Product not found")
        
        if result.modified_count == 1:
            updated_product = await db.products.find_one({"_id": ObjectId(product_id)})
            return clean_object_ids(updated_product)
        else:
            # No changes made (data was identical)
            existing_product = await db.products.find_one({"_id": ObjectId(product_id)})
            return clean_object_ids(existing_product)
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating product: {str(e)}")
        logging.error(f"Product ID: {product_id}")
        logging.error(f"Product data: {product_data}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.delete("/admin/products/{product_id}")
async def delete_product(
    product_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Delete a product (admin only)."""
    try:
        result = await db.products.delete_one({"_id": ObjectId(product_id)})
        if result.deleted_count == 1:
            return {"success": True, "message": "Product deleted successfully"}
        raise HTTPException(status_code=404, detail="Product not found")
    except Exception as e:
        logging.error(f"Error deleting product: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Admin Sales Managers Management
@router.get("/admin/sales_managers")
async def get_all_sales_managers(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        cursor = db.sales_managers.find({})
        items = await cursor.to_list(length=1000)
        return [clean_object_ids(x) for x in items]
    except Exception as e:
        logging.error(f"Error fetching sales managers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post("/admin/sales_managers")
async def create_sales_manager(
    payload: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        from datetime import datetime
        payload["created_at"] = datetime.utcnow()
        payload["updated_at"] = datetime.utcnow()
        if "active" not in payload:
            payload["active"] = True
        result = await db.sales_managers.insert_one(payload)
        created = await db.sales_managers.find_one({"_id": result.inserted_id})
        return clean_object_ids(created)
    except Exception as e:
        logging.error(f"Error creating sales manager: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.put("/admin/sales_managers/{manager_id}")
async def update_sales_manager(
    manager_id: str,
    payload: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        from datetime import datetime
        payload["updated_at"] = datetime.utcnow()
        result = await db.sales_managers.update_one({"_id": ObjectId(manager_id)}, {"$set": payload})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Sales Manager not found")
        updated = await db.sales_managers.find_one({"_id": ObjectId(manager_id)})
        return clean_object_ids(updated)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating sales manager: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.delete("/admin/sales_managers/{manager_id}")
async def delete_sales_manager(
    manager_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        result = await db.sales_managers.delete_one({"_id": ObjectId(manager_id)})
        if result.deleted_count == 1:
            return {"success": True, "message": "Sales Manager deleted successfully"}
        raise HTTPException(status_code=404, detail="Sales Manager not found")
    except Exception as e:
        logging.error(f"Error deleting sales manager: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Admin Directors Management
@router.get("/admin/directors")
async def get_all_directors(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        cursor = db.directors.find({})
        items = await cursor.to_list(length=1000)
        return [clean_object_ids(x) for x in items]
    except Exception as e:
        logging.error(f"Error fetching directors: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post("/admin/directors")
async def create_director(
    payload: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        from datetime import datetime
        payload["created_at"] = datetime.utcnow()
        payload["updated_at"] = datetime.utcnow()
        if "active" not in payload:
            payload["active"] = True
        result = await db.directors.insert_one(payload)
        created = await db.directors.find_one({"_id": result.inserted_id})
        return clean_object_ids(created)
    except Exception as e:
        logging.error(f"Error creating director: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.put("/admin/directors/{director_id}")
async def update_director(
    director_id: str,
    payload: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        from datetime import datetime
        payload["updated_at"] = datetime.utcnow()
        result = await db.directors.update_one({"_id": ObjectId(director_id)}, {"$set": payload})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Director not found")
        updated = await db.directors.find_one({"_id": ObjectId(director_id)})
        return clean_object_ids(updated)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating director: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.delete("/admin/directors/{director_id}")
async def delete_director(
    director_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        result = await db.directors.delete_one({"_id": ObjectId(director_id)})
        if result.deleted_count == 1:
            return {"success": True, "message": "Director deleted successfully"}
        raise HTTPException(status_code=404, detail="Director not found")
    except Exception as e:
        logging.error(f"Error deleting director: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# List orders for a specific salesman (by email or salesman_id)
@router.get("/my-orders")
async def list_my_orders(
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    salesman_id: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Resolve salesman_id from uid (preferred) or email
        if not salesman_id and uid:
            salesman_doc = await db.salesmen.find_one({"firebase_uid": uid})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        if not salesman_id and email:
            import re
            # Case-insensitive exact match on email
            pattern = f"^{re.escape(email)}$"
            salesman_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
            if salesman_doc:
                salesman_id = str(salesman_doc.get("_id"))
        if not salesman_id:
            # If still missing, return empty list (no access)
            return []

        # Prepare filter that matches both ObjectId and raw string storage forms
        salesman_filter_values = [salesman_id]
        try:
            salesman_filter_values.append(ObjectId(salesman_id))
        except Exception:
            pass

        orders_cursor = db.orders.find({"salesman_id": {"$in": salesman_filter_values}})
        orders = await orders_cursor.to_list(length=1000)

        cleaned_orders = []
        for order in orders:
            # Convert _id
            if "_id" in order and order["_id"] is not None:
                order["id"] = str(order["_id"])
                order["_id"] = str(order["_id"])
            # Normalize salesman_id and attach name
            sid = order.get("salesman_id")
            sid_str = str(sid) if sid else ""
            order["salesman_id"] = sid_str
            salesman_name = ""
            salesman_doc = None
            if sid_str:
                # Try ObjectId lookup
                if len(sid_str) == 24:
                    try:
                        salesman_doc = await db.salesmen.find_one({"_id": ObjectId(sid_str)})
                    except Exception:
                        salesman_doc = None
                # Fallback string id lookup
                if not salesman_doc:
                    salesman_doc = await db.salesmen.find_one({"_id": sid_str})
                salesman_name = salesman_doc["name"] if salesman_doc and "name" in salesman_doc else ""
            order["salesman_name"] = salesman_name

            # Normalize dealer_id and attach name
            did = order.get("dealer_id")
            did_str = str(did) if did else ""
            order["dealer_id"] = did_str
            dealer_name = ""
            dealer_doc = None
            if did_str:
                if len(did_str) == 24:
                    try:
                        dealer_doc = await db.dealers.find_one({"_id": ObjectId(did_str)})
                    except Exception:
                        dealer_doc = None
                if not dealer_doc:
                    dealer_doc = await db.dealers.find_one({"_id": did_str})
                dealer_name = dealer_doc["name"] if dealer_doc and "name" in dealer_doc else ""
            order["dealer_name"] = dealer_name

            # Normalize products and attach product names
            products = order.get("products", [])
            if not products and "product_id" in order and order["product_id"] is not None:
                pid = str(order["product_id"])
                product_entry = {
                    "product_id": pid,
                    "quantity": order.get("quantity"),
                    "price": order.get("price"),
                    "product_name": None
                }
                try:
                    product_doc = await db.products.find_one({"_id": ObjectId(pid)})
                    product_entry["product_name"] = product_doc["name"] if product_doc else ""
                    product_entry["gst_percentage"] = product_doc["gst_percentage"] if product_doc else 0
                except Exception:
                    product_entry["product_name"] = ""
                    product_entry["gst_percentage"] = 0
                products = [product_entry]
                order.pop("product_id", None)
                order.pop("quantity", None)
                order.pop("price", None)
                order.pop("product_name", None)
            for p in products:
                pid = p.get("product_id")
                pid_str = str(pid) if pid else ""
                p["product_id"] = pid_str
                product_doc = None
                if not p.get("product_name"):
                    if len(pid_str) == 24:
                        try:
                            product_doc = await db.products.find_one({"_id": ObjectId(pid_str)}, {"name": 1, "gst_percentage": 1})
                        except Exception:
                            product_doc = None
                    if not product_doc:
                        product_doc = await db.products.find_one({"_id": pid_str}, {"name": 1, "gst_percentage": 1})
                    p["product_name"] = product_doc["name"] if product_doc and "name" in product_doc else ""
                    p["gst_percentage"] = product_doc["gst_percentage"] if product_doc and "gst_percentage" in product_doc else 0
            order["products"] = products

            # Clean any remaining ObjectId fields
            order = clean_object_ids(order)
            cleaned_orders.append(order)

        return cleaned_orders
    except Exception as e:
        logging.error(f"Error fetching my orders: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Get current user profile and role
@router.get("/me")
async def get_me(
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        logging.info(f"DEBUG: /me called with uid={uid}, email={email}")
        
        # Require both uid and email for security
        if not email:
            logging.warning("DEBUG: No email provided - denying access")
            raise HTTPException(status_code=400, detail="Email is required for authentication")
            
        doc = None
        # 1. Try to find director by firebase_uid
        if uid:
            doc = await db.directors.find_one({"firebase_uid": uid})
            if doc:
                logging.info(f"DEBUG: Found director by uid: {doc}")
                out = clean_object_ids(doc)
                out["role"] = "director"
                out["is_admin"] = False
                return out
        # 2. Try to find director by email
        if not doc and email:
            import re
            pattern = f"^{re.escape(email)}$"
            doc = await db.directors.find_one({"email": {"$regex": pattern, "$options": "i"}})
            if doc:
                logging.info(f"DEBUG: Found director by email: {doc}")
                # Auto-link Firebase UID if email matched but firebase_uid is not set
                if not doc.get("firebase_uid") and uid:
                    logging.info(f"DEBUG: Director email matched but firebase_uid not set; auto-linking UID {uid}")
                    await db.directors.update_one(
                        {"_id": doc["_id"]}, 
                        {"$set": {"firebase_uid": uid}}
                    )
                    doc["firebase_uid"] = uid  # Update local doc object
                    logging.info(f"DEBUG: Successfully linked Firebase UID {uid} to director {email}")
                out = clean_object_ids(doc)
                out["role"] = "director"
                out["is_admin"] = False
                return out
        # 3. Try to find salesman by firebase_uid
        if uid:
            doc = await db.salesmen.find_one({"firebase_uid": uid})
            logging.info(f"DEBUG: Found salesman by uid: {doc}")
        # 4. Try to find salesman by email
        if not doc and email:
            import re
            pattern = f"^{re.escape(email)}$"
            doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
            logging.info(f"DEBUG: Found salesman by email: {doc}")
            # Auto-link Firebase UID if email matched but firebase_uid is not set
            if doc and not doc.get("firebase_uid") and uid:
                logging.info(f"DEBUG: Email matched but firebase_uid not set; auto-linking UID {uid}")
                await db.salesmen.update_one(
                    {"_id": doc["_id"]}, 
                    {"$set": {"firebase_uid": uid}}
                )
                doc["firebase_uid"] = uid  # Update local doc object
                logging.info(f"DEBUG: Successfully linked Firebase UID {uid} to user {email}")
            elif doc and not doc.get("firebase_uid") and not uid:
                logging.info("DEBUG: Email matched but firebase_uid not set and no uid provided; blocking login.")
                return {"role": "guest", "error": "firebase_uid not set for this user"}
        if not doc:
            logging.info(f"DEBUG: No user found with email {email} - denying access")
            raise HTTPException(status_code=403, detail="Access denied. Email not authorized for this system.")
        role = doc.get("role")
        if role not in ("admin", "sales_manager", "salesman"):
            role = "admin" if doc.get("admin") else "salesman"
        out = clean_object_ids(doc)
        out["role"] = role
        out["is_admin"] = role == "admin"
        logging.info(f"DEBUG: Returning user with role: {role}, full response: {out}")
        return out
    except Exception as e:
        logging.error(f"Error in /me: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# List orders for all salesmen under a Sales Manager (and include manager's own orders)
@router.get("/manager/orders")
async def list_manager_team_orders(
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Get all salesman_ids for this manager (including their own)
        team_ids = await _resolve_manager_team_ids(db, uid, email)
        if not team_ids:
            return []
        # Build $in with both ObjectIds and raw string ids for compatibility
        in_list = []
        for sid in team_ids:
            in_list.append(sid)
            try:
                in_list.append(ObjectId(sid))
            except Exception:
                pass
        orders_cursor = db.orders.find({"salesman_id": {"$in": in_list}})
        orders = await orders_cursor.to_list(length=2000)
        cleaned_orders = []
        for order in orders:
            if "_id" in order and order["_id"] is not None:
                order["id"] = str(order["_id"])
                order["_id"] = str(order["_id"])
            # salesman
            sid = order.get("salesman_id")
            sid_str = str(sid) if sid else ""
            order["salesman_id"] = sid_str
            sdoc = None
            if sid_str:
                if len(sid_str) == 24:
                    try:
                        sdoc = await db.salesmen.find_one({"_id": ObjectId(sid_str)})
                    except Exception:
                        sdoc = None
                if not sdoc:
                    sdoc = await db.salesmen.find_one({"_id": sid_str})
            order["salesman_name"] = sdoc["name"] if sdoc and "name" in sdoc else ""
            # dealer
            did = order.get("dealer_id")
            did_str = str(did) if did else ""
            order["dealer_id"] = did_str
            ddoc = None
            if did_str:
                if len(did_str) == 24:
                    try:
                        ddoc = await db.dealers.find_one({"_id": ObjectId(did_str)})
                    except Exception:
                        ddoc = None
                if not ddoc:
                    ddoc = await db.dealers.find_one({"_id": did_str})
            order["dealer_name"] = ddoc["name"] if ddoc and "name" in ddoc else ""
            # products names
            products = order.get("products", [])
            for p in products:
                pid = p.get("product_id")
                pid_str = str(pid) if pid else ""
                p["product_id"] = pid_str
                if not p.get("product_name"):
                    pdoc = None
                    if len(pid_str) == 24:
                        try:
                            pdoc = await db.products.find_one({"_id": ObjectId(pid_str)}, {"name": 1})
                        except Exception:
                            pdoc = None
                    if not pdoc:
                        pdoc = await db.products.find_one({"_id": pid_str}, {"name": 1})
                    p["product_name"] = pdoc["name"] if pdoc and "name" in pdoc else ""
            order["products"] = products
            cleaned_orders.append(clean_object_ids(order))
        return cleaned_orders
    except Exception as e:
        logging.error(f"Error fetching manager team orders: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Update an order if it belongs to the manager's team (or self)
@router.put("/manager/orders/{order_id}")
async def update_manager_team_order(
    order_id: str,
    payload: dict = Body(...),
    uid: str | None = Query(default=None),
    email: str | None = Query(default=None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # TEST MODE: Allow updates to any order without role/team checks
        try:
            oid = ObjectId(order_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid order id")
        order_doc = await db.orders.find_one({"_id": oid})
        if not order_doc:
            raise HTTPException(status_code=404, detail="Order not found")

        # Prepare update data; normalize products if provided
        update_data = dict(payload or {})
        if "_id" in update_data:
            update_data.pop("_id")
        # If products present, recompute totals and discounts (reuse logic from create)
        products = update_data.get("products")
        if products is not None:
            sum_base = 0.0
            sum_discounted = 0.0
            any_discount = False
            normalized_products = []
            for p in products:
                base = float(p.get("price") or 0)
                pct = p.get("discount_pct")
                discounted_line = p.get("discounted_price")
                if (pct is None or pct == "") and discounted_line not in (None, "") and base > 0:
                    try:
                        discounted_line_val = float(discounted_line)
                        pct = ((base - discounted_line_val) / base) * 100.0
                    except Exception:
                        pct = 0
                if pct in (None, ""):
                    pct = 0
                try:
                    pct = float(pct)
                except Exception:
                    pct = 0
                if pct < 0: pct = 0
                if pct > 30: pct = 30
                if discounted_line in (None, ""):
                    discounted_line = base - (base * pct / 100.0)
                try:
                    discounted_line = float(discounted_line)
                except Exception:
                    discounted_line = base
                line_discount_amt = base - discounted_line
                if line_discount_amt > 0.0000001:
                    any_discount = True
                sum_base += base
                sum_discounted += discounted_line
                p["discount_pct"] = pct
                p["discounted_price"] = discounted_line
                normalized_products.append(p)
            update_data["products"] = normalized_products
            update_data["total_price"] = sum_base
            if sum_base > 0:
                update_data["discounted_total"] = sum_discounted
                update_data["discount"] = ((sum_base - sum_discounted) / sum_base) * 100.0
            else:
                update_data.setdefault("discounted_total", 0)
                update_data.setdefault("discount", 0)
            if any_discount and update_data.get("discount_status") in (None, "", "approved"):
                update_data["discount_status"] = "pending"
            if not any_discount:
                update_data["discount_status"] = "approved"

        from datetime import datetime
        update_data["updated_at"] = datetime.utcnow()
        await db.orders.update_one({"_id": oid}, {"$set": update_data})
        updated = await db.orders.find_one({"_id": oid})
        return clean_object_ids(updated)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating manager order: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Link a Firebase UID to a salesman (by email). Idempotent.
@router.post("/link-uid")
async def link_firebase_uid(
    payload: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Body: { uid: string, email: string }
    Finds salesman by email (case-insensitive) and sets firebase_uid = uid.
    Returns the updated salesman or 404 if not found.
    """
    try:
        import logging
        uid = (payload or {}).get("uid")
        email = (payload or {}).get("email")
        logging.info(f"/link-uid called with email='{email}', uid='{uid}'")
        if not uid or not email:
            logging.warning("/link-uid missing uid or email")
            raise HTTPException(status_code=400, detail="uid and email are required")
        import re
        pattern = f"^{re.escape(email)}$"
        # Try salesmen first
        user_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
        user_type = "salesman"
        # If not found, try sales managers
        if not user_doc:
            user_doc = await db.sales_managers.find_one({"email": {"$regex": pattern, "$options": "i"}})
            user_type = "sales_manager" if user_doc else user_type
        # If not found, try directors
        if not user_doc:
            user_doc = await db.directors.find_one({"email": {"$regex": pattern, "$options": "i"}})
            user_type = "director" if user_doc else user_type
        logging.info(f"/link-uid found {user_type}_doc: {user_doc}")
        if not user_doc:
            logging.warning(f"/link-uid: No user found for email '{email}'")
            raise HTTPException(status_code=404, detail="User not found for email")
        # Update the correct collection
        if user_type == "salesman":
            update_result = await db.salesmen.update_one({"_id": user_doc["_id"]}, {"$set": {"firebase_uid": uid}})
            updated = await db.salesmen.find_one({"_id": user_doc["_id"]})
        elif user_type == "sales_manager":
            update_result = await db.sales_managers.update_one({"_id": user_doc["_id"]}, {"$set": {"firebase_uid": uid}})
            updated = await db.sales_managers.find_one({"_id": user_doc["_id"]})
        elif user_type == "director":
            update_result = await db.directors.update_one({"_id": user_doc["_id"]}, {"$set": {"firebase_uid": uid}})
            updated = await db.directors.find_one({"_id": user_doc["_id"]})
        else:
            raise HTTPException(status_code=500, detail="Unknown user type")
        logging.info(f"/link-uid update_result: matched={update_result.matched_count}, modified={update_result.modified_count}")
        logging.info(f"/link-uid updated {user_type}_doc: {updated}")
        return clean_object_ids(updated)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error linking firebase uid: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Admin utility: clear all firebase_uid fields on salesmen and directors
@router.post("/admin/clear-firebase-uids")
async def admin_clear_firebase_uids(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    try:
        res1 = await db.salesmen.update_many({}, {"$unset": {"firebase_uid": ""}})
        try:
            res2 = await db.directors.update_many({}, {"$unset": {"firebase_uid": ""}})
        except Exception:
            res2 = type("x", (), {"matched_count": 0, "modified_count": 0})()
        try:
            res3 = await db.sales_managers.update_many({}, {"$unset": {"firebase_uid": ""}})
        except Exception:
            res3 = type("x", (), {"matched_count": 0, "modified_count": 0})()
        return {
            "matched_salesmen": res1.matched_count, 
            "modified_salesmen": res1.modified_count, 
            "matched_directors": getattr(res2, 'matched_count', 0), 
            "modified_directors": getattr(res2, 'modified_count', 0),
            "matched_sales_managers": getattr(res3, 'matched_count', 0),
            "modified_sales_managers": getattr(res3, 'modified_count', 0)
        }
    except Exception as e:
        logging.error(f"Error clearing firebase_uids: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Admin utility: clear all orders
@router.post("/admin/clear-all-orders")
async def admin_clear_all_orders(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(admin_check)
):
    """Delete all orders from the database. USE WITH CAUTION!"""
    try:
        result = await db.orders.delete_many({})
        logging.info(f"Deleted {result.deleted_count} orders")
        return {
            "success": True,
            "deleted_count": result.deleted_count,
            "message": f"Successfully deleted {result.deleted_count} orders"
        }
    except Exception as e:
        logging.error(f"Error clearing orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

