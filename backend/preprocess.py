import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import os


def calculate_components(base_salary, overtime_hours, bonus, loan_deduction):
    pf = round(base_salary * 0.12, 2)
    if base_salary < 30000:
        tax = round(base_salary * 0.05, 2)
    elif base_salary < 70000:
        tax = round(base_salary * 0.12, 2)
    else:
        tax = round(base_salary * 0.20, 2)
    insurance = 500.0 if base_salary < 40000 else 1000.0
    overtime_pay = round(overtime_hours * (base_salary / 160.0), 2)
    gross = round(base_salary + overtime_pay + bonus, 2)
    total_deductions = round(pf + tax + insurance + loan_deduction, 2)
    net = round(gross - total_deductions, 2)
    return pf, tax, insurance, overtime_pay, gross, total_deductions, net


def synthesize_employees(n=200, seed=42):
    np.random.seed(seed)
    departments = ["Engineering", "HR", "Finance", "Sales", "Marketing", "Operations"]
    positions = {
        "Engineering": ["Software Engineer", "Senior Engineer", "DevOps", "Data Engineer"],
        "HR": ["HR Executive", "HR Manager"],
        "Finance": ["Accountant", "Analyst", "Finance Manager"],
        "Sales": ["Sales Executive", "Sales Manager"],
        "Marketing": ["SEO Specialist", "Content Marketer", "Brand Manager"],
        "Operations": ["Ops Associate", "Ops Manager"]
    }
    base_by_dept = {
        "Engineering": (45000, 120000),
        "HR": (30000, 70000),
        "Finance": (35000, 90000),
        "Sales": (25000, 80000),
        "Marketing": (28000, 75000),
        "Operations": (25000, 60000)
    }
    records = []
    for i in range(1, n + 1):
        dept = np.random.choice(departments)
        position = np.random.choice(positions[dept])
        low, high = base_by_dept[dept]
        base_salary = float(np.random.randint(low, high))
        name = f"Employee {i}"
        email = f"emp{i}@demo.com"
        joining_year = np.random.choice([2019, 2020, 2021, 2022, 2023, 2024])
        joining_month = np.random.randint(1, 13)
        joining_day = np.random.randint(1, 28)
        joining_date = f"{joining_year:04d}-{joining_month:02d}-{joining_day:02d}"
        records.append({
            "employee_id": i,
            "name": name,
            "email": email,
            "department": dept,
            "position": position,
            "base_salary": base_salary,
            "joining_date": joining_date
        })
    return pd.DataFrame(records)


def generate_monthly_payroll(employees_df, months=("2025-06", "2025-07", "2025-08")):
    rows = []
    for ym in months:
        for _, e in employees_df.iterrows():
            overtime_hours = int(np.random.poisson(5))
            bonus = float(np.random.choice([0, 0, 0, 500, 1000, 2000, 3000]))
            loan_deduction = float(np.random.choice([0, 0, 0, 1000, 2000, 5000]))
            pf, tax, insurance, overtime_pay, gross, total_deductions, net = calculate_components(
                e["base_salary"], overtime_hours, bonus, loan_deduction
            )
            rows.append({
                "employee_id": e["employee_id"],
                "year_month": ym,
                "base_salary": e["base_salary"],
                "overtime_hours": overtime_hours,
                "overtime_pay": overtime_pay,
                "bonus": bonus,
                "pf": pf,
                "tax": tax,
                "insurance": insurance,
                "loan_deduction": loan_deduction,
                "gross_salary": gross,
                "total_deductions": total_deductions,
                "net_salary": net,
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
    return pd.DataFrame(rows)


def main():
    os.makedirs(os.path.join("..", "db"), exist_ok=True)
    os.makedirs(os.path.join("..", "data"), exist_ok=True)
    engine = create_engine("sqlite:///../db/payroll.db", future=True)

    # Create base tables if not exist (align with app)
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
                base_salary REAL,
                joining_date TEXT,
                hashed_password TEXT,
                other_meta TEXT
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
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                role TEXT,
                email TEXT UNIQUE,
                hashed_password TEXT
            );
            """
        ))

    # Synthesize employees and write CSV
    employees_df = synthesize_employees(200)
    employees_csv = os.path.join("..", "data", "sample_hr.csv")
    employees_df.to_csv(employees_csv, index=False)

    # Insert employees
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM employees"))
        for _, row in employees_df.iterrows():
            conn.execute(text(
                "INSERT INTO employees (employee_id, name, email, department, position, base_salary, joining_date) "
                "VALUES (:employee_id, :name, :email, :department, :position, :base_salary, :joining_date)"
            ), row.to_dict())

    # Generate 3 months payroll
    payroll_df = generate_monthly_payroll(employees_df)
    payroll_csv = os.path.join("..", "data", "payroll_monthly.csv")
    payroll_df.to_csv(payroll_csv, index=False)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM payroll_records"))
        for _, row in payroll_df.iterrows():
            conn.execute(text(
                """
                INSERT INTO payroll_records (
                    employee_id, year_month, base_salary, overtime_hours, overtime_pay, bonus, pf, tax,
                    insurance, loan_deduction, gross_salary, total_deductions, net_salary, created_at
                ) VALUES (:employee_id, :year_month, :base_salary, :overtime_hours, :overtime_pay, :bonus, :pf, :tax,
                    :insurance, :loan_deduction, :gross_salary, :total_deductions, :net_salary, :created_at)
                """
            ), row.to_dict())

    # Seed demo users (admin and employee 1) if not present
    import bcrypt
    with engine.begin() as conn:
        admin = conn.execute(text("SELECT id FROM users WHERE email=:e"), {"e": "admin@demo.com"}).fetchone()
        if not admin:
            admin_hash = bcrypt.hashpw("Admin@123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            conn.execute(text("INSERT INTO users (employee_id, role, email, hashed_password) VALUES (NULL, 'admin', 'admin@demo.com', :hp)"), {"hp": admin_hash})
        emp1 = conn.execute(text("SELECT id FROM users WHERE email=:e"), {"e": "emp1@demo.com"}).fetchone()
        if not emp1:
            emp_hash = bcrypt.hashpw("Emp@123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            conn.execute(text("INSERT INTO users (employee_id, role, email, hashed_password) VALUES (1, 'employee', 'emp1@demo.com', :hp)"), {"hp": emp_hash})

    print("Preprocessing done.")


if __name__ == "__main__":
    main()