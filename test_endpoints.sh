#!/bin/bash

# Test script to verify backend endpoints
echo "🧪 Testing NexFarm Backend Endpoints..."

SERVER_URL="http://143.110.181.10"

echo "Testing health check..."
curl -s "$SERVER_URL/health" | python3 -m json.tool

echo -e "\nTesting main endpoint..."
curl -s "$SERVER_URL/" | python3 -m json.tool

echo -e "\nTesting admin salesmen endpoint..."
curl -s "$SERVER_URL/api/orders/admin/salesmen" | python3 -m json.tool

echo -e "\nTesting admin dealers endpoint..."
curl -s "$SERVER_URL/api/orders/admin/dealers" | python3 -m json.tool

echo -e "\nTesting admin products endpoint..."
curl -s "$SERVER_URL/api/orders/admin/products" | python3 -m json.tool

echo -e "\n✅ Endpoint testing complete!"
