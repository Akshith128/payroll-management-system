#!/usr/bin/env python
"""
Diagnostic script to identify why JSON parsing fails
"""
import os
import sys

print("=" * 60)
print("PayrollHR Diagnostic Report")
print("=" * 60)

# Check 1: Database exists
print("\n1. Checking database...")
db_path = os.path.join(os.path.dirname(__file__), 'db', 'payroll.db')
if os.path.exists(db_path):
    db_size = os.path.getsize(db_path) / 1024
    print(f"   ✓ Database exists: {db_path}")
    print(f"   ✓ Size: {db_size:.1f} KB")
else:
    print(f"   ✗ Database NOT found: {db_path}")
    print(f"   → Run: python backend/preprocess.py")

# Check 2: Required Python packages
print("\n2. Checking Python packages...")
required_packages = [
    'flask',
    'flask_cors', 
    'sqlalchemy',
    'bcrypt',
    'jwt',
    'pandas',
    'sklearn'
]
missing = []
for pkg in required_packages:
    try:
        if pkg == 'flask_cors':
            __import__('flask_cors')
        elif pkg == 'jwt':
            __import__('jwt')
        elif pkg == 'sklearn':
            __import__('sklearn')
        else:
            __import__(pkg)
        print(f"   ✓ {pkg}")
    except ImportError:
        print(f"   ✗ {pkg} MISSING")
        missing.append(pkg)

if missing:
    print(f"\n   → Install missing: pip install {' '.join(missing)}")

# Check 3: Frontend file
print("\n3. Checking frontend file...")
frontend_path = os.path.join(os.path.dirname(__file__), 'frontend', 'index.html')
if os.path.exists(frontend_path):
    file_size = os.path.getsize(frontend_path) / 1024
    print(f"   ✓ Frontend exists: {frontend_path}")
    print(f"   ✓ Size: {file_size:.1f} KB")
else:
    print(f"   ✗ Frontend NOT found: {frontend_path}")

# Check 4: Backend app file
print("\n4. Checking backend app...")
app_path = os.path.join(os.path.dirname(__file__), 'backend', 'app.py')
if os.path.exists(app_path):
    print(f"   ✓ Backend app exists: {app_path}")
    # Try to import it
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from backend import app as flask_app
        print(f"   ✓ Backend app imports successfully")
    except Exception as e:
        print(f"   ✗ Backend app import error: {e}")
else:
    print(f"   ✗ Backend NOT found: {app_path}")

print("\n" + "=" * 60)
print("SETUP INSTRUCTIONS:")
print("=" * 60)

if not os.path.exists(db_path):
    print("\n1. Initialize database:")
    print("   python backend/preprocess.py")
    
if missing:
    print("\n2. Install missing packages:")
    print(f"   pip install {' '.join(missing)}")

print("\n3. Start backend server:")
print("   python backend/app.py")
print("   (Should see: Running on http://0.0.0.0:5000)")

print("\n4. Open frontend in browser:")
print("   Open: frontend/index.html")
print("   Or serve with: python -m http.server 8000")

print("\n5. Test login:")
print("   Email: admin@demo.com")
print("   Password: Admin@123")

print("\n" + "=" * 60)
print("If you still get 'Unexpected end of JSON input' error:")
print("=" * 60)
print("1. Check browser DevTools (F12) → Network tab")
print("2. Look for red requests (errors)")
print("3. Click request → Response tab")
print("4. Show the response content")
print("5. This will show what's actually being returned")
print("\n")
