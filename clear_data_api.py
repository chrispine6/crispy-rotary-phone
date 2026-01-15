"""
Script to clear Firebase UIDs and all order data via API endpoints.
This uses the admin API endpoints which include proper authentication.
"""

import requests
import sys

# API Configuration
API_BASE_URL = "https://nexgrow-server.vercel.app/api"
# Alternatively, for local testing:
# API_BASE_URL = "http://localhost:8000"

def clear_firebase_uids():
    """Clear all Firebase UIDs via API endpoint."""
    try:
        print("\n" + "="*60)
        print("CLEARING FIREBASE UIDs")
        print("="*60)
        
        url = f"{API_BASE_URL}/orders/admin/clear-firebase-uids"
        
        print(f"Calling: {url}")
        print("Note: This requires admin authentication via Firebase")
        
        # You'll need to include authentication headers
        # This is a placeholder - adjust based on your auth setup
        response = requests.post(url)
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✓ Salesmen: Matched {result.get('matched_salesmen', 0)}, Modified {result.get('modified_salesmen', 0)}")
            print(f"✓ Sales Managers: Matched {result.get('matched_sales_managers', 0)}, Modified {result.get('modified_sales_managers', 0)}")
            print(f"✓ Directors: Matched {result.get('matched_directors', 0)}, Modified {result.get('modified_directors', 0)}")
            
            total = (
                result.get('modified_salesmen', 0) + 
                result.get('modified_sales_managers', 0) + 
                result.get('modified_directors', 0)
            )
            print(f"\nTotal Firebase UIDs cleared: {total}")
            return True
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

def clear_all_orders():
    """Delete all orders via API endpoint."""
    try:
        print("\n" + "="*60)
        print("CLEARING ALL ORDERS")
        print("="*60)
        
        confirm = input("\n⚠️  ARE YOU SURE you want to delete ALL orders? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("\n❌ Order deletion cancelled.")
            return False
        
        url = f"{API_BASE_URL}/orders/admin/clear-all-orders"
        
        print(f"Calling: {url}")
        print("Note: This requires admin authentication via Firebase")
        
        response = requests.post(url)
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✓ Successfully deleted {result.get('deleted_count', 0)} orders")
            return True
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

def main():
    """Main function."""
    print("\n" + "="*60)
    print("DATA CLEARING SCRIPT (API-based)")
    print("="*60)
    print("This script will:")
    print("1. Clear all Firebase UIDs from salesmen, sales managers, and directors")
    print("2. Delete all orders from the database")
    print("\n⚠️  WARNING: This operation cannot be undone!")
    print("⚠️  NOTE: You must be authenticated as an admin!")
    print("="*60)
    
    proceed = input("\nDo you want to proceed? (yes/no): ")
    
    if proceed.lower() != 'yes':
        print("\n❌ Operation cancelled.")
        return
    
    print("\nWhat would you like to clear?")
    print("1. Clear Firebase UIDs only")
    print("2. Clear all orders only")
    print("3. Clear both Firebase UIDs and orders")
    
    choice = input("\nEnter your choice (1/2/3): ").strip()
    
    success_uids = False
    success_orders = False
    
    if choice in ['1', '3']:
        success_uids = clear_firebase_uids()
    
    if choice in ['2', '3']:
        success_orders = clear_all_orders()
    
    # Summary
    print("\n" + "="*60)
    print("OPERATION SUMMARY")
    print("="*60)
    if choice in ['1', '3']:
        print(f"Firebase UIDs: {'✓ Cleared' if success_uids else '❌ Failed'}")
    if choice in ['2', '3']:
        print(f"Orders: {'✓ Deleted' if success_orders else '❌ Failed'}")
    print("="*60)

if __name__ == "__main__":
    main()
