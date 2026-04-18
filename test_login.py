#!/usr/bin/env python
"""
Quick test script to validate login functionality
"""
import requests
import json

API_URL = "http://localhost:5000/api"

def test_login():
    """Test login with demo credentials"""
    print("\n=== Testing Login ===")
    
    # Test admin login
    print("\n1. Testing admin login (admin@demo.com)...")
    response = requests.post(
        f"{API_URL}/login",
        json={"email": "admin@demo.com", "password": "Admin@123"},
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    if response.status_code == 200:
        token = data.get('token')
        user = data.get('user')
        print(f"✓ Admin login successful!")
        print(f"  Token: {token[:50]}..." if token else "  No token returned!")
        print(f"  User: {user}")
        
        # Test using token for another request
        print("\n2. Testing authenticated request with token...")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        me_response = requests.get(f"{API_URL}/me", headers=headers)
        print(f"Status: {me_response.status_code}")
        print(f"Response: {json.dumps(me_response.json(), indent=2)}")
    else:
        print(f"✗ Admin login failed!")
    
    # Test employee login
    print("\n3. Testing employee login (emp1@demo.com)...")
    response = requests.post(
        f"{API_URL}/login",
        json={"email": "emp1@demo.com", "password": "Emp@123"},
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    if response.status_code == 200:
        print(f"✓ Employee login successful!")
    else:
        print(f"✗ Employee login failed!")

    # Test invalid credentials
    print("\n4. Testing invalid credentials...")
    response = requests.post(
        f"{API_URL}/login",
        json={"email": "admin@demo.com", "password": "WrongPassword"},
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    if response.status_code != 200:
        print(f"✓ Correctly rejected invalid credentials")

if __name__ == "__main__":
    print("Testing PayrollHR API Login")
    print("Make sure the backend is running on http://localhost:5000")
    try:
        test_login()
    except requests.exceptions.ConnectionError:
        print("\n✗ ERROR: Could not connect to http://localhost:5000")
        print("Please ensure the Flask backend is running:")
        print("  python backend/app.py")
