# logic for making orders

from fastapi import APIRouter, Depends, HTTPException, Query, Body
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
    
    # Check total documents in dealers collection
    total_count = await db.dealers.count_documents({})
    logging.info(f"Total dealers in database: {total_count}")
    
    # Convert salesman_id to ObjectId and search for dealers
    dealers_cursor = db.dealers.find(
        {"sales_man_id": ObjectId(salesman_id)},
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
        doc = await db.products.find_one({"name": name}, {"_id": 1, "name": 1})
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
            state_raw = (order_dict.get("state") or "").strip().upper() or "NA"
            # Determine fiscal year (Apr 1 - Mar 31)
            if now.month < 4:
                start_year = now.year - 1
            else:
                start_year = now.year
            start_year_short = str(start_year)[-2:]
            end_year_short = str(start_year + 1)[-2:]
            fiscal_year_str = f"{start_year_short}-{end_year_short}"  # e.g. 24-25
            # Atomic counter per FY+state. First visible code should end 1000.
            counter_doc = await db.order_counters.find_one_and_update(
                {"fiscal_year": fiscal_year_str, "state": state_raw},
                {"$inc": {"seq": 1}, "$setOnInsert": {"seq": 0}},
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
            seq_val = counter_doc.get("seq", 0)
            # seq_val starts at 1 for first order -> produce 1000
            code_tail = f"1{seq_val-1:03d}" if seq_val > 0 else "1000"
            order_dict["order_code"] = f"nxg-{fiscal_year_str}-{state_raw}-{code_tail}"
        except Exception as gen_ex:
            logging.error(f"Order code generation failed: {gen_ex}")
        # --- END ORDER CODE LOGIC ---
        # Ensure '_id' is not set for new orders
        order_dict.pop("_id", None)
        result = await db.orders.insert_one(order_dict)
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Order creation failed")
        order_dict["_id"] = result.inserted_id
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
    # Clean ObjectId fields before returning
    cleaned_orders = [clean_object_ids(order) for order in orders]
    return cleaned_orders

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
                except Exception:
                    product_entry["product_name"] = ""
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
                            product_doc = await db.products.find_one({"_id": ObjectId(pid_str)}, {"name": 1})
                        except Exception:
                            product_doc = None
                    if not product_doc:
                        product_doc = await db.products.find_one({"_id": pid_str}, {"name": 1})
                    p["product_name"] = product_doc["name"] if product_doc and "name" in product_doc else ""
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
        doc = None
        if uid:
            doc = await db.salesmen.find_one({"firebase_uid": uid})
        if not doc and email:
            import re
            pattern = f"^{re.escape(email)}$"
            doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
        if not doc:
            return {"role": "guest"}
        role = doc.get("role")
        if role not in ("admin", "sales_manager", "salesman"):
            role = "admin" if doc.get("admin") else "salesman"
        out = clean_object_ids(doc)
        out["role"] = role
        out["is_admin"] = role == "admin"
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
        # TEST MODE: For testing, treat every user as manager of every salesman.
        # Return all orders regardless of role or team linkage.
        orders_cursor = db.orders.find({})
        orders = await orders_cursor.to_list(length=5000)
        # Reuse cleaning from admin/my-orders path
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
        uid = (payload or {}).get("uid")
        email = (payload or {}).get("email")
        if not uid or not email:
            raise HTTPException(status_code=400, detail="uid and email are required")
        import re
        pattern = f"^{re.escape(email)}$"
        salesman_doc = await db.salesmen.find_one({"email": {"$regex": pattern, "$options": "i"}})
        if not salesman_doc:
            raise HTTPException(status_code=404, detail="Salesman not found for email")
        await db.salesmen.update_one({"_id": salesman_doc["_id"]}, {"$set": {"firebase_uid": uid}})
        updated = await db.salesmen.find_one({"_id": salesman_doc["_id"]})
        return clean_object_ids(updated)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error linking firebase uid: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")