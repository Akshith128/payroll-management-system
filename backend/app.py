"""
Main Flask application for the Payroll Management System
Provides REST API endpoints for employee management, payroll processing,
anomaly detection, forecasting, and payslip generation.
"""

from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
import pandas as pd
from sqlalchemy import create_engine, text
import bcrypt
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import logging
import jwt
import re
import secrets

# Import our custom modules
from payroll import PayrollProcessor
from anomaly import AnomalyDetector
from forecast import PayrollForecaster
from generate_payslip import PayslipGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'payroll_system_secret_key_2024'
JWT_SECRET = os.environ.get('JWT_SECRET', 'jwt_secret_key_2024')
JWT_ALG = 'HS256'
CORS(app, supports_credentials=True, origins=['http://localhost:5000', 'http://127.0.0.1:5000'])

# Database configuration
db_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'payroll.db')
DATABASE_URL = f"sqlite:///{os.path.abspath(db_path)}"
engine = create_engine(DATABASE_URL, future=True)
def _is_valid_email(email: str) -> bool:
    if not isinstance(email, str):
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def _is_strong_password(pw: str) -> bool:
    if not isinstance(pw, str) or len(pw) < 8:
        return False
    has_upper = any(c.isupper() for c in pw)
    has_lower = any(c.islower() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    has_symbol = any(not c.isalnum() for c in pw)
    return has_upper and has_lower and has_digit and has_symbol


def create_tables_and_seed():
    """Create required tables if they don't exist and seed demo users."""
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER UNIQUE,
                name TEXT,
                email TEXT,
                department TEXT,
                position TEXT,
                phone TEXT,
                base_salary REAL,
                joining_date TEXT,
                hashed_password TEXT,
                leave_balance REAL DEFAULT 21.0,
                other_meta TEXT
            );
            """
        ))
        
        # Add leave_balance column if it doesn't exist (for existing databases)
        try:
            conn.execute(text("ALTER TABLE employees ADD COLUMN leave_balance REAL DEFAULT 21.0"))
        except Exception:
            pass  # Column already exists
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS salary_structures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER UNIQUE,
                basic_pay REAL,
                allowances REAL DEFAULT 0,
                overtime_rate REAL DEFAULT 0,
                tax_rate REAL DEFAULT 0.12,
                pf_rate REAL DEFAULT 0.12,
                effective_date TEXT
            );
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS payroll_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                year_month TEXT,
                base_salary REAL,
                overtime_hours REAL,
                overtime_pay REAL,
                bonus REAL,
                pf REAL,
                tax REAL,
                insurance REAL,
                loan_deduction REAL,
                gross_salary REAL,
                total_deductions REAL,
                net_salary REAL,
                created_at TEXT
            );
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS anomalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payroll_record_id INTEGER,
                score REAL,
                is_anomaly INTEGER,
                details TEXT
            );
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT,
                year_month TEXT,
                predicted_gross REAL,
                confidence_score REAL
            );
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                role TEXT,
                email TEXT UNIQUE,
                hashed_password TEXT,
                is_verified INTEGER DEFAULT 0,
                reset_token TEXT,
                reset_expires_at TEXT
            );
            """
        ))
        
        # Add missing columns if they don't exist (for existing databases)
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0"))
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_token TEXT"))
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_expires_at TEXT"))
        except Exception:
            pass  # Column already exists

        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                date TEXT,
                status TEXT,
                working_hours REAL
            );
            """
        ))

        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS leaves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                date TEXT,
                reason TEXT,
                status TEXT
            );
            """
        ))

        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tax_rate REAL DEFAULT 0.12,
                pf_rate REAL DEFAULT 0.12,
                overtime_rate REAL DEFAULT 1.0,
                leave_deduction_rate REAL DEFAULT 0.0
            );
            """
        ))

        # Seed admin and demo employee users if not present
        admin = conn.execute(text("SELECT id FROM users WHERE email=:e"), {"e": "admin@demo.com"}).fetchone()
        if not admin:
            admin_hash = bcrypt.hashpw("Admin@123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            conn.execute(text(
                "INSERT INTO users (employee_id, role, email, hashed_password, is_verified) VALUES (:emp, :role, :email, :hp, 1)"
            ), {"emp": None, "role": "admin", "email": "admin@demo.com", "hp": admin_hash})
        else:
            # Ensure existing admin user is verified
            conn.execute(text("UPDATE users SET is_verified=1 WHERE email=:e"), {"e": "admin@demo.com"})

        emp_user = conn.execute(text("SELECT id FROM users WHERE email=:e"), {"e": "emp1@demo.com"}).fetchone()
        if not emp_user:
            # also ensure employee with employee_id 1 exists minimally
            exists = conn.execute(text("SELECT id FROM employees WHERE employee_id=1")).fetchone()
            if not exists:
                conn.execute(text(
                    "INSERT INTO employees (employee_id, name, email, department, position, base_salary, joining_date) "
                    "VALUES (1, 'John Doe', 'emp1@demo.com', 'Engineering', 'Software Engineer', 50000, '2023-01-01')"
                ))
            emp_hash = bcrypt.hashpw("Emp@123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            conn.execute(text(
                "INSERT INTO users (employee_id, role, email, hashed_password, is_verified) VALUES (:emp, :role, :email, :hp, 1)"
            ), {"emp": 1, "role": "employee", "email": "emp1@demo.com", "hp": emp_hash})
        else:
            # Ensure existing employee user is verified
            conn.execute(text("UPDATE users SET is_verified=1 WHERE email=:e"), {"e": "emp1@demo.com"})

        # Seed some sample attendance data if none exists
        attendance_count = conn.execute(text("SELECT COUNT(*) as c FROM attendance")).fetchone().c
        if attendance_count == 0:
            # Add sample attendance records for the demo employee
            sample_attendance = [
                (1, '2024-10-01', 'Present', 8.0),
                (1, '2024-10-02', 'Present', 8.0),
                (1, '2024-10-03', 'Present', 7.5),
                (1, '2024-10-04', 'Absent', 0.0),
                (1, '2024-10-05', 'Present', 8.0),
                (1, '2024-10-06', 'Leave', 0.0),
                (1, '2024-10-07', 'Present', 8.0),
                (1, '2024-10-08', 'Present', 8.0),
                (1, '2024-10-09', 'Present', 8.0),
                (1, '2024-10-10', 'Present', 8.0),
            ]
            for emp_id, date, status, hours in sample_attendance:
                conn.execute(text(
                    "INSERT INTO attendance (employee_id, date, status, working_hours) VALUES (:eid, :d, :s, :h)"
                ), {"eid": emp_id, "d": date, "s": status, "h": hours})


# Initialize services
payroll_processor = PayrollProcessor(engine)
anomaly_detector = AnomalyDetector(engine)
forecaster = PayrollForecaster(engine)
payslip_generator = PayslipGenerator(engine)


def _get_token_user():
    """Return user payload from Authorization Bearer token if present and valid."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth.split(' ', 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            return payload
        except Exception:
            return None
    return None


def require_auth(f):
    def decorated_function(*args, **kwargs):
        token_user = _get_token_user()
        if token_user:
            request.user = token_user
        else:
            logger.info(f"Session data: {dict(session)}")
            if 'user_id' not in session:
                logger.warning("Authentication required - no user_id in session or token invalid")
                return jsonify({'error': 'Authentication required'}), 401
            request.user = {
                'id': session.get('user_id'),
                'employee_id': session.get('employee_id'),
                'role': session.get('role'),
                'email': session.get('email')
            }
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


def require_admin(f):
    def decorated_function(*args, **kwargs):
        token_user = _get_token_user()
        if token_user:
            if token_user.get('role') != 'admin':
                return jsonify({'error': 'Admin access required'}), 403
            request.user = token_user
        else:
            logger.info(f"Admin check - Session data: {dict(session)}")
            if 'user_id' not in session or session.get('role') != 'admin':
                logger.warning(f"Admin access required - user_id: {session.get('user_id')}, role: {session.get('role')}")
                return jsonify({'error': 'Admin access required'}), 403
            request.user = {
                'id': session.get('user_id'),
                'employee_id': session.get('employee_id'),
                'role': session.get('role'),
                'email': session.get('email')
            }
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


# Authentication endpoints
def _make_jwt(user_row):
    payload = {
        'id': user_row.id,
        'employee_id': user_row.employee_id,
        'role': user_row.role,
        'email': user_row.email,
        'exp': datetime.utcnow() + timedelta(hours=12)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
@app.route('/api/users', methods=['GET'])
@require_admin
def list_users():
    try:
        with engine.begin() as conn:
            df = pd.read_sql(text("SELECT id, employee_id, role, email, is_verified FROM users ORDER BY id"), conn)
        return jsonify(df.to_dict(orient='records'))
    except Exception as e:
        logger.error(f"List users error: {str(e)}")
        return jsonify({'error': 'Failed to list users'}), 500


@app.route('/api/users/<int:user_id>/verify', methods=['POST'])
@require_admin
def verify_user(user_id: int):
    try:
        with engine.begin() as conn:
            res = conn.execute(text("UPDATE users SET is_verified=1 WHERE id=:id"), {"id": user_id})
            if res.rowcount == 0:
                return jsonify({'error': 'User not found'}), 404
        return jsonify({'message': 'User verified'})
    except Exception as e:
        logger.error(f"Verify user error: {str(e)}")
        return jsonify({'error': 'Verification failed'}), 500



@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    role = (data.get('role') or 'employee').strip()
    employee_id = data.get('employee_id')

    # Public registration only allows employee role
    if role != 'employee':
        return jsonify({'error': 'Only employee self-registration allowed'}), 400
    if not _is_valid_email(email):
        return jsonify({'error': 'Invalid email'}), 400
    if not _is_strong_password(password):
        return jsonify({'error': 'Weak password'}), 400

    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        with engine.begin() as conn:
            # If employee_id not provided, try to infer from employees table by email
            if not employee_id:
                row = conn.execute(text("SELECT employee_id FROM employees WHERE lower(email)=:e"), {"e": email}).fetchone()
                employee_id = row.employee_id if row else None
            conn.execute(text(
                "INSERT INTO users (employee_id, role, email, hashed_password, is_verified) VALUES (:emp, :role, :email, :hp, 0)"
            ), {"emp": employee_id, "role": 'employee', "email": email, "hp": pw_hash})
        return jsonify({'message': 'Registration submitted. Await admin verification.'}), 201
    except Exception as e:
        logger.error(f"Register error: {str(e)}")
        return jsonify({'error': 'Registration failed'}), 500


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    logger.info(f"Login attempt for email: {email}")
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    try:
        with engine.begin() as conn:
            query = text("SELECT id, employee_id, role, email, hashed_password, is_verified FROM users WHERE lower(email) = :email")
            result = conn.execute(query, {"email": email}).fetchone()
        logger.info(f"Database query result: {result}")
        if not result:
            logger.warning(f"No user found for email: {email}")
            return jsonify({'error': 'Invalid credentials'}), 401
        if getattr(result, 'is_verified', 0) != 1:
            logger.warning(f"User {email} not verified")
            return jsonify({'error': 'Account not verified by admin yet'}), 403
        if bcrypt.checkpw(password.encode('utf-8'), result.hashed_password.encode('utf-8')):
            logger.info(f"Successful login for {email}")
            # keep session for existing frontend
            session['user_id'] = result.id
            session['employee_id'] = result.employee_id
            session['role'] = result.role
            session['email'] = result.email
            token = _make_jwt(result)
            return jsonify({'message': 'Login successful', 'token': token, 'user': {'id': result.id, 'employee_id': result.employee_id, 'role': result.role, 'email': result.email}})
        logger.warning(f"Password check failed for {email}")
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Login failed'}), 500


# Password reset
@app.route('/api/password/reset/request', methods=['POST'])
def request_password_reset():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not _is_valid_email(email):
        return jsonify({'error': 'Invalid email'}), 400
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
    try:
        with engine.begin() as conn:
            res = conn.execute(text("UPDATE users SET reset_token=:t, reset_expires_at=:e WHERE lower(email)=:em"), {"t": token, "e": expires_at, "em": email})
            # Do not reveal whether email exists
        # TODO: integrate with email service to send token link
        return jsonify({'message': 'If the email exists, a reset link was sent', 'token_debug': token if os.environ.get('ENV') == 'dev' else None})
    except Exception as e:
        logger.error(f"Reset request error: {str(e)}")
        return jsonify({'error': 'Could not initiate reset'}), 500


@app.route('/api/password/reset', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    token = data.get('token')
    new_password = data.get('password')
    if not token or not _is_strong_password(new_password):
        return jsonify({'error': 'Invalid token or weak password'}), 400
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT id, reset_expires_at FROM users WHERE reset_token=:t"), {"t": token}).fetchone()
            if not row:
                return jsonify({'error': 'Invalid token'}), 400
            if row.reset_expires_at and datetime.fromisoformat(row.reset_expires_at) < datetime.utcnow():
                return jsonify({'error': 'Token expired'}), 400
            pw_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            conn.execute(text("UPDATE users SET hashed_password=:hp, reset_token=NULL, reset_expires_at=NULL WHERE id=:id"), {"hp": pw_hash, "id": row.id})
        return jsonify({'message': 'Password updated'})
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        return jsonify({'error': 'Password reset failed'}), 500


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'})


@app.route('/api/me', methods=['GET'])
@require_auth
def get_current_user():
    return jsonify({'user_id': session['user_id'], 'employee_id': session.get('employee_id'), 'role': session.get('role'), 'email': session.get('email')})


# Employee management
@app.route('/api/employees', methods=['GET'])
@require_admin
def list_employees():
    dept = request.args.get('department')
    try:
        limit = int(request.args.get('limit', 25))
        offset = int(request.args.get('offset', 0))
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
    except Exception:
        limit, offset = 25, 0

    with engine.begin() as conn:
        if dept:
            total = conn.execute(text("SELECT COUNT(*) as c FROM employees WHERE department=:d"), {"d": dept}).fetchone().c
            df = pd.read_sql(text("SELECT * FROM employees WHERE department=:d ORDER BY employee_id LIMIT :limit OFFSET :offset"), conn, params={"d": dept, "limit": limit, "offset": offset})
        else:
            total = conn.execute(text("SELECT COUNT(*) as c FROM employees")).fetchone().c
            df = pd.read_sql(text("SELECT * FROM employees ORDER BY employee_id LIMIT :limit OFFSET :offset"), conn, params={"limit": limit, "offset": offset})
    return jsonify({"total": int(total), "limit": limit, "offset": offset, "rows": df.to_dict(orient='records')})


@app.route('/api/employees', methods=['POST'])
@require_admin
def add_employee():
    data = request.get_json() or {}
    # Validate inputs
    for key in ['name', 'email', 'department', 'position', 'base_salary']:
        if key not in data or data[key] in (None, ''):
            return jsonify({'error': f'Missing required field: {key}'}), 400
    try:
        base_salary = float(data['base_salary'])
        if base_salary <= 0:
            return jsonify({'error': 'base_salary must be positive'}), 400
    except Exception:
        return jsonify({'error': 'base_salary must be a number'}), 400

    with engine.begin() as conn:
        # Auto-generate employee_id if not provided
        emp_id = data.get('employee_id')
        if not emp_id:
            row = conn.execute(text("SELECT COALESCE(MAX(employee_id), 0) + 1 AS next_id FROM employees")).fetchone()
            emp_id = int(row.next_id)
        # Insert employee
        conn.execute(text(
            "INSERT INTO employees (employee_id, name, email, department, position, phone, base_salary, joining_date) "
            "VALUES (:employee_id, :name, :email, :department, :position, :phone, :base_salary, :joining_date)"
        ), {
            'employee_id': emp_id,
            'name': data['name'],
            'email': data['email'],
            'department': data['department'],
            'position': data['position'],
            'phone': data.get('phone'),
            'base_salary': base_salary,
            'joining_date': data.get('joining_date', datetime.now().strftime('%Y-%m-%d'))
        })
        # Create default salary structure
        conn.execute(text(
            "INSERT OR REPLACE INTO salary_structures (employee_id, basic_pay, allowances, overtime_rate, tax_rate, pf_rate, effective_date) "
            "VALUES (:employee_id, :basic_pay, :allowances, :overtime_rate, :tax_rate, :pf_rate, :effective_date)"
        ), {
            'employee_id': emp_id,
            'basic_pay': base_salary,
            'allowances': float(data.get('allowances', 0) or 0),
            'overtime_rate': float(data.get('overtime_rate', 0) or 0),
            'tax_rate': float(data.get('tax_rate', 0.12) or 0.12),
            'pf_rate': float(data.get('pf_rate', 0.12) or 0.12),
            'effective_date': datetime.now().strftime('%Y-%m-%d')
        })
    return jsonify({'message': 'Employee added', 'employee_id': emp_id})


@app.route('/api/employees/<int:employee_id>', methods=['GET'])
@require_auth
def get_employee(employee_id):
    # employee can only view self
    user = getattr(request, 'user', {})
    if user.get('role') == 'employee' and user.get('employee_id') != employee_id:
        return jsonify({'error': 'Forbidden'}), 403
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM employees WHERE employee_id=:eid"), {"eid": employee_id}).mappings().fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))


@app.route('/api/employees/<int:employee_id>', methods=['PUT'])
@require_admin
def update_employee(employee_id):
    data = request.get_json() or {}
    allowed = ['name', 'email', 'department', 'position', 'phone', 'base_salary', 'joining_date']
    sets = [f"{k} = :{k}" for k in allowed if k in data]
    if not sets:
        return jsonify({'error': 'No updatable fields provided'}), 400
    q = text(f"UPDATE employees SET {', '.join(sets)} WHERE employee_id = :eid")
    with engine.begin() as conn:
        conn.execute(q, {**{k: data[k] for k in data if k in allowed}, 'eid': employee_id})
        # If base_salary provided, sync salary structure
        if 'base_salary' in data:
            conn.execute(text(
                "INSERT OR REPLACE INTO salary_structures (employee_id, basic_pay, allowances, overtime_rate, tax_rate, pf_rate, effective_date) "
                "VALUES (:employee_id, :basic_pay, COALESCE((SELECT allowances FROM salary_structures WHERE employee_id=:employee_id), 0), "
                "COALESCE((SELECT overtime_rate FROM salary_structures WHERE employee_id=:employee_id), 0), "
                "COALESCE((SELECT tax_rate FROM salary_structures WHERE employee_id=:employee_id), 0.12), "
                "COALESCE((SELECT pf_rate FROM salary_structures WHERE employee_id=:employee_id), 0.12), :effective_date)"
            ), {
                'employee_id': employee_id,
                'basic_pay': float(data['base_salary']),
                'effective_date': datetime.now().strftime('%Y-%m-%d')
            })
    return jsonify({'message': 'Employee updated'})


@app.route('/api/employees/<int:employee_id>', methods=['DELETE'])
@require_admin
def delete_employee(employee_id):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM employees WHERE employee_id=:eid"), {"eid": employee_id})
        conn.execute(text("DELETE FROM users WHERE employee_id=:eid"), {"eid": employee_id})
    return jsonify({'message': 'Employee deleted'})


@app.route('/api/employees/upload', methods=['POST'])
@require_admin
def upload_employees_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'CSV file required'}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    if not filename.lower().endswith('.csv'):
        return jsonify({'error': 'Only CSV files allowed'}), 400
    tmp_path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    file.save(tmp_path)
    result = payroll_processor.import_employees_from_csv(tmp_path)
    return jsonify({'message': 'Upload processed', **result})


# Payroll processing
@app.route('/api/payroll/run', methods=['POST'])
@require_admin
def run_payroll():
    data = request.get_json() or {}
    year_month = data.get('year_month') or datetime.now().strftime('%Y-%m')
    result = payroll_processor.process_monthly_payroll(year_month)
    return jsonify({'message': 'Payroll processed', 'summary': result})


@app.route('/api/payroll/<int:employee_id>', methods=['GET'])
@require_auth
def get_employee_payroll(employee_id):
    if session.get('role') == 'employee' and session.get('employee_id') != employee_id:
        return jsonify({'error': 'Forbidden'}), 403
    year_month = request.args.get('month')
    with engine.begin() as conn:
        if year_month:
            df = pd.read_sql(text("SELECT * FROM payroll_records WHERE employee_id=:eid AND year_month=:ym ORDER BY year_month DESC"), conn, params={"eid": employee_id, "ym": year_month})
        else:
            df = pd.read_sql(text("SELECT * FROM payroll_records WHERE employee_id=:eid ORDER BY year_month DESC"), conn, params={"eid": employee_id})
    return jsonify(df.to_dict(orient='records'))


# Admin list of payroll records for a month, to link payslip downloads
@app.route('/api/payroll/list', methods=['GET'])
@require_admin
def list_payroll_by_month():
    year_month = request.args.get('month') or datetime.now().strftime('%Y-%m')
    with engine.begin() as conn:
        df = pd.read_sql(text(
            """
            SELECT pr.employee_id,
                   e.name,
                   e.email,
                   e.department,
                   e.position,
                   pr.year_month,
                   pr.gross_salary,
                   pr.total_deductions,
                   pr.net_salary
            FROM payroll_records pr
            JOIN employees e ON pr.employee_id = e.employee_id
            WHERE pr.year_month = :ym
            ORDER BY e.department, e.name
            """
        ), conn, params={'ym': year_month})
    return jsonify(df.to_dict(orient='records'))

# Attendance & Leave
@app.route('/api/attendance', methods=['POST'])
@require_auth
def add_attendance():
    data = request.get_json() or {}
    employee_id = data.get('employee_id')
    date_str = data.get('date') or datetime.now().strftime('%Y-%m-%d')
    status = data.get('status')
    working_hours = float(data.get('working_hours', 0))
    if not employee_id or status not in ('Present', 'Absent', 'Leave'):
        return jsonify({'error': 'employee_id and valid status required'}), 400
    # employees can only submit for self
    user = getattr(request, 'user', {})
    if user.get('role') == 'employee' and user.get('employee_id') != employee_id:
        return jsonify({'error': 'Forbidden'}), 403
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO attendance (employee_id, date, status, working_hours) VALUES (:eid, :d, :s, :h)"
        ), {"eid": employee_id, "d": date_str, "s": status, "h": working_hours})
    return jsonify({'message': 'Attendance recorded'})


@app.route('/api/attendance/<int:employee_id>', methods=['GET'])
@require_auth
def get_attendance(employee_id):
    user = getattr(request, 'user', {})
    if user.get('role') == 'employee' and user.get('employee_id') != employee_id:
        return jsonify({'error': 'Forbidden'}), 403
    # Pagination
    try:
        limit = int(request.args.get('limit', 25))
        offset = int(request.args.get('offset', 0))
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
    except Exception:
        limit, offset = 25, 0
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) as c FROM attendance WHERE employee_id=:eid"), {"eid": employee_id}).fetchone().c
        df = pd.read_sql(text("SELECT * FROM attendance WHERE employee_id=:eid ORDER BY date DESC LIMIT :limit OFFSET :offset"), conn, params={"eid": employee_id, "limit": limit, "offset": offset})
    return jsonify({"total": int(total), "limit": limit, "offset": offset, "rows": df.to_dict(orient='records')})


@app.route('/api/leave', methods=['POST'])
@require_auth
def submit_leave():
    data = request.get_json() or {}
    employee_id = data.get('employee_id')
    date_str = data.get('date') or datetime.now().strftime('%Y-%m-%d')
    reason = data.get('reason', '')
    user = getattr(request, 'user', {})
    if user.get('role') == 'employee' and user.get('employee_id') != employee_id:
        return jsonify({'error': 'Forbidden'}), 403
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO leaves (employee_id, date, reason, status) VALUES (:eid, :d, :r, 'pending')"
        ), {"eid": employee_id, "d": date_str, "r": reason})
    return jsonify({'message': 'Leave submitted'})


@app.route('/api/leave', methods=['GET'])
@require_admin
def list_leaves():
    with engine.begin() as conn:
        df = pd.read_sql(text("SELECT * FROM leaves ORDER BY date DESC"), conn)
    return jsonify(df.to_dict(orient='records'))


@app.route('/api/leave/<int:leave_id>/approve', methods=['POST'])
@require_admin
def approve_leave(leave_id):
    try:
        with engine.begin() as conn:
            # Get leave details
            leave_row = conn.execute(text("SELECT employee_id, date FROM leaves WHERE id=:id"), {"id": leave_id}).fetchone()
            if not leave_row:
                return jsonify({'error': 'Leave request not found'}), 404
            
            # Check if employee has sufficient leave balance
            emp_row = conn.execute(text("SELECT leave_balance FROM employees WHERE employee_id=:eid"), {"eid": leave_row.employee_id}).fetchone()
            if not emp_row or emp_row.leave_balance < 1.0:
                return jsonify({'error': 'Insufficient leave balance'}), 400
            
            # Update leave status to approved
            conn.execute(text("UPDATE leaves SET status='approved' WHERE id=:id"), {"id": leave_id})
            
            # Deduct leave balance (assuming 1 day per leave request)
            conn.execute(text(
                "UPDATE employees SET leave_balance = leave_balance - 1.0 WHERE employee_id=:eid"
            ), {"eid": leave_row.employee_id})
            
            # Mark attendance as Leave for that date
            conn.execute(text(
                "INSERT OR REPLACE INTO attendance (employee_id, date, status, working_hours) VALUES (:eid, :d, 'Leave', 0)"
            ), {"eid": leave_row.employee_id, "d": leave_row.date})
            
        return jsonify({'message': 'Leave approved successfully and balance deducted'})
    except Exception as e:
        logger.error(f"Approve leave error: {str(e)}")
        return jsonify({'error': 'Failed to approve leave'}), 500


@app.route('/api/leave/<int:leave_id>/reject', methods=['POST'])
@require_admin
def reject_leave(leave_id):
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE leaves SET status='rejected' WHERE id=:id"), {"id": leave_id})
        return jsonify({'message': 'Leave rejected successfully'})
    except Exception as e:
        logger.error(f"Reject leave error: {str(e)}")
        return jsonify({'error': 'Failed to reject leave'}), 500


@app.route('/api/attendance/all', methods=['GET'])
@require_admin
def get_all_attendance():
    """Get attendance logs for all employees with pagination"""
    try:
        limit = int(request.args.get('limit', 25))
        offset = int(request.args.get('offset', 0))
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
    except Exception:
        limit, offset = 25, 0
    
    employee_id = request.args.get('employee_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    with engine.begin() as conn:
        # Build dynamic query
        where_conditions = []
        params = {"limit": limit, "offset": offset}
        
        if employee_id:
            where_conditions.append("a.employee_id = :employee_id")
            params["employee_id"] = int(employee_id)
        
        if date_from:
            where_conditions.append("a.date >= :date_from")
            params["date_from"] = date_from
            
        if date_to:
            where_conditions.append("a.date <= :date_to")
            params["date_to"] = date_to
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        query = f"""
            SELECT a.*, e.name, e.email, e.department, e.position
            FROM attendance a
            JOIN employees e ON a.employee_id = e.employee_id
            {where_clause}
            ORDER BY a.date DESC, e.name
            LIMIT :limit OFFSET :offset
        """
        
        df = pd.read_sql(text(query), conn, params=params)
        
        # Get total count
        count_query = f"""
            SELECT COUNT(*) as total
            FROM attendance a
            JOIN employees e ON a.employee_id = e.employee_id
            {where_clause}
        """
        total = conn.execute(text(count_query), params).fetchone().total
        
    return jsonify({
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "rows": df.to_dict(orient='records')
    })


@app.route('/api/attendance/<int:attendance_id>', methods=['PUT'])
@require_admin
def update_attendance(attendance_id):
    """Update attendance record manually"""
    data = request.get_json() or {}
    status = data.get('status')
    working_hours = data.get('working_hours')
    
    if status not in ('Present', 'Absent', 'Leave'):
        return jsonify({'error': 'Invalid status'}), 400
    
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE attendance SET status=:status, working_hours=:hours WHERE id=:id"
            ), {"status": status, "hours": float(working_hours or 0), "id": attendance_id})
            
        return jsonify({'message': 'Attendance updated successfully'})
    except Exception as e:
        logger.error(f"Update attendance error: {str(e)}")
        return jsonify({'error': 'Failed to update attendance'}), 500


@app.route('/api/attendance/summary', methods=['GET'])
@require_admin
def get_attendance_summary():
    """Generate monthly attendance summary with pagination"""
    year_month = request.args.get('month') or datetime.now().strftime('%Y-%m')
    limit = min(int(request.args.get('limit', 10)), 50)  # Default 10, max 50
    offset = int(request.args.get('offset', 0))
    
    try:
        with engine.begin() as conn:
            # Get total count first
            count_query = text("""
                SELECT COUNT(DISTINCT e.employee_id) as total
                FROM employees e
                LEFT JOIN attendance a ON e.employee_id = a.employee_id 
                    AND strftime('%Y-%m', a.date) = :year_month
            """)
            total_count = conn.execute(count_query, {"year_month": year_month}).fetchone().total
            
            # Get paginated attendance summary for the month
            query = text("""
                SELECT 
                    e.employee_id,
                    e.name,
                    e.department,
                    e.position,
                    COUNT(CASE WHEN a.status = 'Present' THEN 1 END) as present_days,
                    COUNT(CASE WHEN a.status = 'Absent' THEN 1 END) as absent_days,
                    COUNT(CASE WHEN a.status = 'Leave' THEN 1 END) as leave_days,
                    SUM(CASE WHEN a.status = 'Present' THEN a.working_hours ELSE 0 END) as total_hours,
                    COUNT(*) as total_days
                FROM employees e
                LEFT JOIN attendance a ON e.employee_id = a.employee_id 
                    AND strftime('%Y-%m', a.date) = :year_month
                GROUP BY e.employee_id, e.name, e.department, e.position
                ORDER BY e.department, e.name
                LIMIT :limit OFFSET :offset
            """)
            
            df = pd.read_sql(query, conn, params={"year_month": year_month, "limit": limit, "offset": offset})
            
            # Calculate summary statistics (using all data, not just paginated)
            stats_query = text("""
                SELECT 
                    COUNT(DISTINCT e.employee_id) as total_employees,
                    SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as total_present_days,
                    SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as total_absent_days,
                    SUM(CASE WHEN a.status = 'Leave' THEN 1 ELSE 0 END) as total_leave_days,
                    SUM(CASE WHEN a.status = 'Present' THEN a.working_hours ELSE 0 END) as total_working_hours,
                    COUNT(a.id) as total_days
                FROM employees e
                LEFT JOIN attendance a ON e.employee_id = a.employee_id 
                    AND strftime('%Y-%m', a.date) = :year_month
            """)
            
            stats_result = conn.execute(stats_query, {"year_month": year_month}).fetchone()
            
            summary_stats = {
                "total_employees": stats_result.total_employees or 0,
                "total_present_days": int(stats_result.total_present_days or 0),
                "total_absent_days": int(stats_result.total_absent_days or 0),
                "total_leave_days": int(stats_result.total_leave_days or 0),
                "total_working_hours": float(stats_result.total_working_hours or 0),
                "average_attendance_rate": float((stats_result.total_present_days / stats_result.total_days * 100) if stats_result.total_days and stats_result.total_days > 0 else 0)
            }
            
        return jsonify({
            "month": year_month,
            "summary": summary_stats,
            "details": df.to_dict(orient='records'),
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            }
        })
    except Exception as e:
        logger.error(f"Attendance summary error: {str(e)}")
        return jsonify({'error': 'Failed to generate attendance summary'}), 500


@app.route('/api/attendance/seed', methods=['POST'])
@require_admin
def seed_attendance_data():
    """Seed sample attendance data for testing"""
    try:
        with engine.begin() as conn:
            # Check if we have employees
            emp_count = conn.execute(text("SELECT COUNT(*) as c FROM employees")).fetchone().c
            if emp_count == 0:
                return jsonify({'error': 'No employees found. Add employees first.'}), 400
            
            # Get first few employees
            employees = conn.execute(text("SELECT employee_id FROM employees LIMIT 5")).fetchall()
            
            # Add sample attendance for each employee
            import random
            from datetime import datetime, timedelta
            
            base_date = datetime(2024, 10, 1)
            attendance_data = []
            
            for emp_row in employees:
                emp_id = emp_row.employee_id
                for i in range(20):  # 20 days of data
                    date = base_date + timedelta(days=i)
                    date_str = date.strftime('%Y-%m-%d')
                    
                    # Random attendance status
                    status_options = ['Present', 'Present', 'Present', 'Present', 'Absent', 'Leave']
                    status = random.choice(status_options)
                    
                    # Random working hours
                    if status == 'Present':
                        hours = random.uniform(7.0, 9.0)
                    else:
                        hours = 0.0
                    
                    attendance_data.append((emp_id, date_str, status, hours))
            
            # Insert attendance data
            for emp_id, date_str, status, hours in attendance_data:
                conn.execute(text(
                    "INSERT OR IGNORE INTO attendance (employee_id, date, status, working_hours) VALUES (:eid, :d, :s, :h)"
                ), {"eid": emp_id, "d": date_str, "s": status, "h": hours})
            
        return jsonify({'message': f'Seeded {len(attendance_data)} attendance records'})
    except Exception as e:
        logger.error(f"Seed attendance error: {str(e)}")
        return jsonify({'error': 'Failed to seed attendance data'}), 500


@app.route('/api/employees/leave-balances', methods=['GET'])
@require_admin
def get_leave_balances():
    """Get leave balances for all employees with pagination"""
    try:
        limit = int(request.args.get('limit', 10))  # Default to 10 records
        offset = int(request.args.get('offset', 0))
        limit = max(1, min(limit, 50))  # Max 50 per page
        offset = max(0, offset)
    except Exception:
        limit, offset = 10, 0
    
    with engine.begin() as conn:
        # Get paginated results
        df = pd.read_sql(text("""
            SELECT employee_id, name, email, department, position, leave_balance
            FROM employees 
            ORDER BY department, name
            LIMIT :limit OFFSET :offset
        """), conn, params={"limit": limit, "offset": offset})
        
        # Get total count
        total = conn.execute(text("SELECT COUNT(*) as total FROM employees")).fetchone().total
        
    return jsonify({
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "rows": df.to_dict(orient='records')
    })


@app.route('/api/employees/<int:employee_id>/leave-balance', methods=['PUT'])
@require_admin
def update_leave_balance(employee_id):
    """Manually update employee leave balance"""
    data = request.get_json() or {}
    new_balance = data.get('leave_balance')
    
    if new_balance is None or new_balance < 0:
        return jsonify({'error': 'Invalid leave balance'}), 400
    
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE employees SET leave_balance=:balance WHERE employee_id=:eid"
            ), {"balance": float(new_balance), "eid": employee_id})
            
        return jsonify({'message': 'Leave balance updated successfully'})
    except Exception as e:
        logger.error(f"Update leave balance error: {str(e)}")
        return jsonify({'error': 'Failed to update leave balance'}), 500


@app.route('/api/attendance/upload', methods=['POST'])
@require_admin
def upload_attendance_csv():
    """Upload CSV with columns: employee_id,date,status,working_hours"""
    if 'file' not in request.files:
        return jsonify({'error': 'CSV file required'}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    if not filename.lower().endswith('.csv'):
        return jsonify({'error': 'Only CSV files allowed'}), 400
    tmp_path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    file.save(tmp_path)
    try:
        df = pd.read_csv(tmp_path)
        # Normalize columns
        df.columns = [c.strip().lower() for c in df.columns]
        required = {'employee_id', 'date', 'status'}
        missing = required - set(df.columns)
        if missing:
            return jsonify({'error': f'Missing required columns: {sorted(list(missing))}'}), 400
        if 'working_hours' not in df.columns:
            df['working_hours'] = 0
        # Basic validation
        valid_status = {'Present', 'Absent', 'Leave'}
        records = []
        for _, row in df.iterrows():
            try:
                eid = int(row['employee_id'])
                date_str = str(row['date'])
                status = str(row['status']).strip().capitalize()
                hours = float(row.get('working_hours', 0) or 0)
                if status not in valid_status:
                    continue
                records.append({'eid': eid, 'd': date_str, 's': status, 'h': hours})
            except Exception:
                continue
        inserted = 0
        with engine.begin() as conn:
            for r in records:
                conn.execute(text(
                    "INSERT INTO attendance (employee_id, date, status, working_hours) VALUES (:eid, :d, :s, :h)"
                ), r)
                inserted += 1
        return jsonify({'message': 'Upload processed', 'inserted': inserted})
    except Exception as e:
        return jsonify({'error': 'Failed to process CSV', 'details': str(e)}), 500


# Payslip generation
@app.route('/api/payslip/<int:employee_id>', methods=['GET'])
@require_auth
def payslip(employee_id):
    if session.get('role') == 'employee' and session.get('employee_id') != employee_id:
        return jsonify({'error': 'Forbidden'}), 403
    year_month = request.args.get('month') or datetime.now().strftime('%Y-%m')
    try:
        filepath = payslip_generator.generate_payslip(employee_id, year_month)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# Anomaly detection
@app.route('/api/run-anomaly', methods=['POST'])
@require_admin
def run_anomaly():
    contamination = float(request.args.get('contamination', 0.02))
    months = int(request.args.get('months', 6))
    max_rows = int(request.args.get('max_rows', 5000))
    result = anomaly_detector.detect_anomalies(contamination=contamination, months=months, max_rows=max_rows)
    return jsonify(result)


@app.route('/api/anomalies', methods=['GET'])
@require_admin
def list_anomalies():
    """Get anomalies with pagination"""
    try:
        limit = min(int(request.args.get('limit', 10)), 50)  # Default 10, max 50
        offset = int(request.args.get('offset', 0))
    except Exception:
        limit, offset = 10, 0
    
    with engine.begin() as conn:
        # Get total count first
        try:
            count_query = text("SELECT COUNT(*) as total FROM anomalies")
            total_count = conn.execute(count_query).fetchone().total
        except Exception:
            total_count = 0
        
        # Get paginated anomalies
        try:
            query = text("SELECT * FROM anomalies ORDER BY id DESC LIMIT :limit OFFSET :offset")
            df = pd.read_sql(query, conn, params={"limit": limit, "offset": offset})
        except Exception:
            query = text("SELECT rowid as id, * FROM anomalies ORDER BY rowid DESC LIMIT :limit OFFSET :offset")
            df = pd.read_sql(query, conn, params={"limit": limit, "offset": offset})
    
    return jsonify({
        "anomalies": df.to_dict(orient='records'),
        "pagination": {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }
    })


# Forecasting
@app.route('/api/forecast', methods=['GET'])
@require_admin
def forecast():
    months = int(request.args.get('months', 3))
    year = request.args.get('year')
    start = request.args.get('start')  # YYYY-MM
    target_year = None
    try:
        if year:
            target_year = int(year)
    except Exception:
        target_year = None
    total = forecaster.generate_forecasts(months_ahead=months, target_year=target_year, start_year_month=start)
    
    # Add pagination for forecasts
    try:
        limit = min(int(request.args.get('limit', 10)), 50)  # Default 10, max 50
        offset = int(request.args.get('offset', 0))
    except Exception:
        limit, offset = 10, 0
    
    with engine.begin() as conn:
        # Get total count
        count_query = text("SELECT COUNT(*) as total FROM forecasts")
        total_count = conn.execute(count_query).fetchone().total
        
        # Get paginated forecasts
        df = pd.read_sql(text("SELECT * FROM forecasts ORDER BY year_month, department LIMIT :limit OFFSET :offset"), conn, params={"limit": limit, "offset": offset})
    
    return jsonify({
        'generated': total, 
        'forecasts': df.to_dict(orient='records'),
        'pagination': {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }
    })


# Reports & Analytics
@app.route('/api/payroll/report', methods=['GET'])
@require_admin
def payroll_report():
    with engine.begin() as conn:
        df = pd.read_sql(text(
            """
            SELECT pr.year_month,
                   COUNT(*) as employees,
                   SUM(pr.gross_salary) as total_gross,
                   SUM(pr.total_deductions) as total_deductions,
                   SUM(pr.net_salary) as total_net
            FROM payroll_records pr
            GROUP BY pr.year_month
            ORDER BY pr.year_month DESC
            """
        ), conn)
    return jsonify(df.to_dict(orient='records'))


@app.route('/api/dashboard/summary', methods=['GET'])
@require_admin
def dashboard_summary():
    with engine.begin() as conn:
        total_employees = conn.execute(text("SELECT COUNT(*) as c FROM employees")).fetchone().c
        total_payroll = conn.execute(text("SELECT SUM(net_salary) as s FROM payroll_records")).fetchone().s or 0
        monthly = pd.read_sql(text("SELECT year_month, SUM(net_salary) as total_net FROM payroll_records GROUP BY year_month ORDER BY year_month"), conn)
    return jsonify({
        'total_employees': int(total_employees),
        'total_payroll_cost': float(total_payroll),
        'monthly_trends': monthly.to_dict(orient='records')
    })


@app.route('/api/dashboard/department/<string:department>', methods=['GET'])
@require_admin
def department_report(department):
    with engine.begin() as conn:
        df = pd.read_sql(text(
            """
            SELECT e.department, pr.year_month,
                   SUM(pr.gross_salary) as total_gross,
                   SUM(pr.total_deductions) as total_deductions,
                   SUM(pr.net_salary) as total_net
            FROM payroll_records pr
            JOIN employees e ON pr.employee_id = e.employee_id
            WHERE e.department = :d
            GROUP BY e.department, pr.year_month
            ORDER BY pr.year_month
            """
        ), conn, params={'d': department})
    return jsonify(df.to_dict(orient='records'))


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


# Bootstrap demo data for past months
@app.route('/api/bootstrap', methods=['POST'])
@require_admin
def bootstrap_demo():
    try:
        months = int(request.args.get('months', 3))  # Reduced to 3 months
        # ensure there are some employees
        with engine.begin() as conn:
            cnt = conn.execute(text('SELECT COUNT(*) as c FROM employees')).fetchone()
            if not cnt or cnt.c == 0:
                # create a few demo employees
                conn.execute(text("""
                    INSERT INTO employees (employee_id, name, email, department, position, base_salary, joining_date)
                    VALUES
                    (2, 'Jane Smith', 'emp2@demo.com', 'Engineering', 'QA Engineer', 42000, '2023-03-01'),
                    (3, 'Bob Lee', 'emp3@demo.com', 'Finance', 'Accountant', 48000, '2022-11-01'),
                    (4, 'Alice Wong', 'emp4@demo.com', 'HR', 'HR Specialist', 45000, '2022-07-15')
                """))
        # run payroll for past N months (limited)
        from datetime import date
        today = date.today()
        generated = []
        for i in range(months, 0, -1):
            year = today.year
            month = today.month - i
            while month <= 0:
                month += 12
                year -= 1
            ym = f"{year}-{month:02d}"
            summary = payroll_processor.process_monthly_payroll(ym)
            generated.append({'year_month': ym, **summary})
        return jsonify({'message': 'Bootstrapped demo payroll', 'generated_months': len(generated), 'details': generated})
    except Exception as e:
        logger.error(f"Bootstrap error: {str(e)}")
        return jsonify({'error': 'Bootstrap failed', 'details': str(e)}), 500


# Serve frontend
@app.route('/')
def serve_frontend():
    frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html')
    return send_file(frontend_path)


create_tables_and_seed()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)