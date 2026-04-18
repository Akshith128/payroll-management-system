import math
from sqlalchemy import create_engine, text
from backend.payroll import PayrollProcessor


def test_calculate_payroll_basic():
    engine = create_engine("sqlite://")
    pp = PayrollProcessor(engine)

    # Base salary at different slabs
    cases = [
        (25000, 10, 1000, 0, 0.05, 500),   # tax 5%, insurance 500
        (50000, 0, 0, 0, 0.12, 1000),      # tax 12%, insurance 1000
        (80000, 5, 2000, 500, 0.20, 1000), # tax 20%, insurance 1000
    ]

    for base, ot, bonus, loan, tax_rate, insurance in cases:
        res = pp.calculate_payroll(base, ot, bonus, loan)
        assert math.isclose(res['pf'], base*0.12, rel_tol=1e-6)
        assert math.isclose(res['tax'], base*tax_rate, rel_tol=1e-6)
        assert res['insurance'] == insurance
        assert math.isclose(res['overtime_pay'], ot*(base/160.0), rel_tol=1e-6)
        gross = base + res['overtime_pay'] + bonus
        deductions = res['pf'] + res['tax'] + insurance + loan
        assert math.isclose(res['gross_salary'], gross, rel_tol=1e-6)
        assert math.isclose(res['total_deductions'], deductions, rel_tol=1e-6)
        assert math.isclose(res['net_salary'], gross - deductions, rel_tol=1e-6)


