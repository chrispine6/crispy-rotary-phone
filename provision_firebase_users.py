#!/usr/bin/env python3
"""
One-time script: Creates Firebase Email/Password accounts for every
salesman & director in MongoDB, then links the Firebase UID back.

Usage:
    python provision_firebase_users.py --password "YourSharedPassword123"

Run from the crispy-rotary-phone directory with the venv active.
GOOGLE_APPLICATION_CREDENTIALS must point to the service-account JSON, OR
place firebase-service-account.json in the same directory as this script.
"""

import argparse
import asyncio
import os
import sys
import re

# ── Auto-locate service account JSON ──────────────────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_default_sa = os.path.join(_script_dir, "firebase-service-account.json")
if os.path.exists(_default_sa) and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _default_sa
    print(f"Using service account: {_default_sa}")

# ── Imports ────────────────────────────────────────────────────────────────────
try:
    import firebase_admin
    from firebase_admin import auth as fb_auth, credentials as fb_cred
except ImportError:
    print("ERROR: firebase-admin not installed. Run:  pip install firebase-admin")
    sys.exit(1)

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# ── Config ─────────────────────────────────────────────────────────────────────
MONGODB_URL = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://nexfarm_admin:sgFeiUpVjWwuv84W@cluster0.aicbbge.mongodb.net/"
    "?retryWrites=true&w=majority&appName=Cluster0"
)
DB_NAME = "nexfarm_db"


async def provision(password: str, dry_run: bool = False):
    # Init Firebase
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()

    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]

    created = []
    skipped = []
    failed = []

    # Collect emails from salesmen + directors
    all_docs = []  # list of (email, collection_name)
    for col in ("salesmen", "directors"):
        cursor = db[col].find({}, {"email": 1, "firebase_uid": 1})
        docs = await cursor.to_list(length=5000)
        for doc in docs:
            email = (doc.get("email") or "").strip().lower()
            if email:
                all_docs.append((email, col, doc.get("_id")))

    print(f"\nFound {len(all_docs)} users across salesmen + directors collections.\n")

    for email, col, doc_id in all_docs:
        try:
            # Check if Firebase account already exists
            try:
                existing = fb_auth.get_user_by_email(email)
                print(f"  SKIP  {email}  (already exists, uid={existing.uid})")
                skipped.append(email)
                # Link UID if missing in MongoDB
                if not dry_run:
                    await db[col].update_one(
                        {"_id": doc_id, "firebase_uid": {"$exists": False}},
                        {"$set": {"firebase_uid": existing.uid}}
                    )
                continue
            except fb_auth.UserNotFoundError:
                pass

            if dry_run:
                print(f"  DRY   {email}  (would create)")
                created.append(email)
                continue

            fb_user = fb_auth.create_user(email=email, password=password)
            print(f"  OK    {email}  -> uid={fb_user.uid}")
            created.append(email)

            # Link UID into MongoDB
            await db[col].update_one(
                {"_id": doc_id},
                {"$set": {"firebase_uid": fb_user.uid}}
            )

        except Exception as e:
            print(f"  FAIL  {email}  -> {e}")
            failed.append((email, str(e)))

    client.close()

    print("\n" + "=" * 60)
    print(f"  Created : {len(created)}")
    print(f"  Skipped : {len(skipped)}")
    print(f"  Failed  : {len(failed)}")
    print("=" * 60)
    if failed:
        print("\nFailed emails:")
        for e, reason in failed:
            print(f"  {e}: {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provision Firebase users from MongoDB")
    parser.add_argument("--password", required=True, help="Shared password for all users (min 6 chars)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    args = parser.parse_args()

    if len(args.password) < 6:
        print("ERROR: password must be at least 6 characters")
        sys.exit(1)

    asyncio.run(provision(args.password, dry_run=args.dry_run))
