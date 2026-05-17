#!/bin/bash
# Test dashboard API endpoints

echo "Testing Dashboard API Endpoints"
echo "================================"
echo ""

echo "1. Testing /api/state from localhost:"
curl -s http://localhost:5000/api/state | python3 -m json.tool
echo ""

echo "2. Testing /api/network from localhost:"
curl -s http://localhost:5000/api/network | python3 -m json.tool
echo ""

echo "3. Testing /api/state from 10.42.0.1:"
curl -s http://10.42.0.1:5000/api/state | python3 -m json.tool
echo ""

echo "4. Testing /api/network from 10.42.0.1:"
curl -s http://10.42.0.1:5000/api/network | python3 -m json.tool
echo ""

echo "5. Testing main page:"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://10.42.0.1:5000/
