"""
Payslip generation module using FPDF
Generates professional PDF payslips for employees
"""

import pandas as pd
from sqlalchemy import create_engine, text
from fpdf import FPDF
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

class PayslipGenerator:
    def __init__(self, engine):
        self.engine = engine
    
    def generate_payslip(self, employee_id, year_month):
        """
        Generate payslip PDF for a specific employee and month
        """
        try:
            # Get employee and payroll data
            query = text("""
                SELECT 
                    e.employee_id, e.name, e.email, e.department, e.position,
                    e.joining_date, e.base_salary,
                    pr.year_month, pr.overtime_hours, pr.overtime_pay, pr.bonus,
                    pr.pf, pr.tax, pr.insurance, pr.loan_deduction,
                    pr.gross_salary, pr.total_deductions, pr.net_salary,
                    pr.created_at
                FROM employees e
                JOIN payroll_records pr ON e.employee_id = pr.employee_id
                WHERE e.employee_id = :employee_id AND pr.year_month = :year_month
            """)
            
            # SQLAlchemy 2.x: use an explicit connection/transaction
            with self.engine.begin() as conn:
                result = conn.execute(
                    query,
                    {
                        'employee_id': employee_id,
                        'year_month': year_month
                    }
                ).fetchone()
            
            if not result:
                raise ValueError(f"No payroll record found for employee {employee_id} in {year_month}")
            
            # Create PDF
            pdf = FPDF()
            pdf.add_page()
            
            # Set font
            pdf.set_font('Arial', 'B', 16)
            
            # Company header
            pdf.cell(0, 10, 'PAYSLIP', 0, 1, 'C')
            pdf.ln(5)
            
            # Company details
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 5, 'ABC Company Ltd.', 0, 1, 'C')
            pdf.cell(0, 5, '123 Business Street, City, State 12345', 0, 1, 'C')
            pdf.cell(0, 5, 'Phone: (555) 123-4567 | Email: hr@abccompany.com', 0, 1, 'C')
            pdf.ln(10)
            
            # Payslip period
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, f'Pay Period: {year_month}', 0, 1, 'C')
            pdf.ln(5)
            
            # Employee details
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(40, 6, 'Employee ID:', 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(60, 6, str(result.employee_id), 0, 0)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(40, 6, 'Department:', 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, result.department, 0, 1)
            
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(40, 6, 'Employee Name:', 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(60, 6, result.name, 0, 0)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(40, 6, 'Position:', 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, result.position, 0, 1)
            
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(40, 6, 'Email:', 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(60, 6, result.email, 0, 0)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(40, 6, 'Joining Date:', 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, str(result.joining_date), 0, 1)
            
            pdf.ln(10)
            
            # Earnings section
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, 'EARNINGS', 0, 1)
            pdf.set_font('Arial', '', 10)
            
            # Earnings table
            pdf.cell(100, 6, 'Description', 1, 0, 'L')
            pdf.cell(40, 6, 'Amount', 1, 1, 'R')
            
            pdf.cell(100, 6, 'Basic Salary', 1, 0, 'L')
            pdf.cell(40, 6, f'${result.base_salary:,.2f}', 1, 1, 'R')
            
            if result.overtime_pay > 0:
                pdf.cell(100, 6, f'Overtime Pay ({result.overtime_hours} hrs)', 1, 0, 'L')
                pdf.cell(40, 6, f'${result.overtime_pay:,.2f}', 1, 1, 'R')
            
            if result.bonus > 0:
                pdf.cell(100, 6, 'Bonus', 1, 0, 'L')
                pdf.cell(40, 6, f'${result.bonus:,.2f}', 1, 1, 'R')
            
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(100, 6, 'Total Gross Salary', 1, 0, 'L')
            pdf.cell(40, 6, f'${result.gross_salary:,.2f}', 1, 1, 'R')
            
            pdf.ln(5)
            
            # Deductions section
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, 'DEDUCTIONS', 0, 1)
            pdf.set_font('Arial', '', 10)
            
            # Deductions table
            pdf.cell(100, 6, 'Description', 1, 0, 'L')
            pdf.cell(40, 6, 'Amount', 1, 1, 'R')
            
            pdf.cell(100, 6, 'Provident Fund (12%)', 1, 0, 'L')
            pdf.cell(40, 6, f'${result.pf:,.2f}', 1, 1, 'R')
            
            pdf.cell(100, 6, 'Income Tax', 1, 0, 'L')
            pdf.cell(40, 6, f'${result.tax:,.2f}', 1, 1, 'R')
            
            pdf.cell(100, 6, 'Insurance', 1, 0, 'L')
            pdf.cell(40, 6, f'${result.insurance:,.2f}', 1, 1, 'R')
            
            if result.loan_deduction > 0:
                pdf.cell(100, 6, 'Loan Deduction', 1, 0, 'L')
                pdf.cell(40, 6, f'${result.loan_deduction:,.2f}', 1, 1, 'R')
            
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(100, 6, 'Total Deductions', 1, 0, 'L')
            pdf.cell(40, 6, f'${result.total_deductions:,.2f}', 1, 1, 'R')
            
            pdf.ln(5)
            
            # Net salary
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(100, 8, 'NET SALARY', 1, 0, 'L')
            pdf.cell(40, 8, f'${result.net_salary:,.2f}', 1, 1, 'R')
            
            pdf.ln(10)
            
            # Footer
            pdf.set_font('Arial', '', 8)
            pdf.cell(0, 5, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
            pdf.cell(0, 5, 'This is a computer-generated payslip. No signature required.', 0, 1, 'C')
            
            # Save PDF
            filename = f'payslip_emp_{employee_id}_{year_month}.pdf'
            filepath = os.path.join('..', 'backend', filename)
            pdf.output(filepath)
            
            logger.info(f"Generated payslip for employee {employee_id} for {year_month}")
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating payslip: {str(e)}")
            raise

def main():
    """
    Command line interface for generating payslips
    """
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python generate_payslip.py <employee_id>")
        sys.exit(1)
    
    employee_id = int(sys.argv[1])
    
    # Get current month
    current_month = datetime.now().strftime('%Y-%m')
    
    # Initialize generator
    engine = create_engine("sqlite:///../db/payroll.db")
    generator = PayslipGenerator(engine)
    
    try:
        filepath = generator.generate_payslip(employee_id, current_month)
        print(f"Payslip generated: {filepath}")
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()