import pandas as pd
from sqlalchemy import create_engine, text
from backend.anomaly import AnomalyDetector


def seed(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE employees (id INTEGER PRIMARY KEY, employee_id INTEGER, department TEXT, position TEXT, base_salary REAL)"))
        conn.execute(text("CREATE TABLE payroll_records (id INTEGER PRIMARY KEY, employee_id INTEGER, year_month TEXT, base_salary REAL, overtime_hours REAL, overtime_pay REAL, bonus REAL, pf REAL, tax REAL, insurance REAL, loan_deduction REAL, gross_salary REAL, total_deductions REAL, net_salary REAL, created_at TEXT)"))
        conn.execute(text("CREATE TABLE anomalies (id INTEGER PRIMARY KEY, payroll_record_id INTEGER, score REAL, is_anomaly INTEGER, details TEXT)"))
        # Normal cluster
        for i in range(1, 51):
            conn.execute(text("INSERT INTO employees(employee_id, department, position, base_salary) VALUES (:e,'Eng','SE',40000)"), {"e": i})
            conn.execute(text("INSERT INTO payroll_records(employee_id, year_month, base_salary, overtime_hours, overtime_pay, bonus, pf, tax, insurance, loan_deduction, gross_salary, total_deductions, net_salary, created_at) VALUES (:e,'2025-08',40000,5,1250,500,4800,4800,1000,0,41750,10600,31150,'2025-08-31')"), {"e": i})
        # Inject anomalies (very high bonus)
        for i in range(51, 56):
            conn.execute(text("INSERT INTO employees(employee_id, department, position, base_salary) VALUES (:e,'Eng','SE',40000)"), {"e": i})
            conn.execute(text("INSERT INTO payroll_records(employee_id, year_month, base_salary, overtime_hours, overtime_pay, bonus, pf, tax, insurance, loan_deduction, gross_salary, total_deductions, net_salary, created_at) VALUES (:e,'2025-08',40000,5,1250,20000,4800,4800,1000,0,61250,10600,50650,'2025-08-31')"), {"e": i})


def test_anomaly_detection_marks_injected():
    engine = create_engine("sqlite://", future=True)
    seed(engine)
    det = AnomalyDetector(engine)
    res = det.detect_anomalies(contamination=0.05)
    assert res['total_records'] == 55
    # Should mark close to 5% anomalies (>= 3)
    assert res['anomaly_count'] >= 3


