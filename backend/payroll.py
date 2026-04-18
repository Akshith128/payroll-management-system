"""
Payroll processing module
Handles payroll calculations, deductions, and monthly payroll runs
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PayrollProcessor:
    def __init__(self, engine):
        self.engine = engine
    
    def calculate_payroll(self, base_salary, overtime_hours=0, bonus=0, loan_deduction=0):
        """
        Calculate payroll components based on business rules
        
        Rules:
        - PF = 12% of base_salary
        - Tax: base < 30000 => 5%; 30000 ≤ base < 70000 => 12%; base ≥ 70000 => 20%
        - Insurance: base < 40000 => 500; else 1000
        - Overtime pay = overtime_hours * (base_salary / 160)
        - Net salary = base + overtime_pay + bonus - (pf + tax + insurance + loan)
        """
        
        # Calculate PF (Provident Fund)
        pf = base_salary * 0.12
        
        # Calculate Tax based on salary slabs
        if base_salary < 30000:
            tax = base_salary * 0.05
        elif base_salary < 70000:
            tax = base_salary * 0.12
        else:
            tax = base_salary * 0.20
        
        # Calculate Insurance
        insurance = 500 if base_salary < 40000 else 1000
        
        # Calculate Overtime Pay
        overtime_pay = overtime_hours * (base_salary / 160)
        
        # Calculate totals
        gross_salary = base_salary + overtime_pay + bonus
        total_deductions = pf + tax + insurance + loan_deduction
        net_salary = gross_salary - total_deductions
        
        return {
            'base_salary': base_salary,
            'overtime_hours': overtime_hours,
            'overtime_pay': overtime_pay,
            'bonus': bonus,
            'pf': pf,
            'tax': tax,
            'insurance': insurance,
            'loan_deduction': loan_deduction,
            'gross_salary': gross_salary,
            'total_deductions': total_deductions,
            'net_salary': net_salary
        }
    
    def process_monthly_payroll(self, year_month):
        """
        Process payroll for all employees for a specific month (limited to prevent lag)
        """
        try:
            # Get employees with limit to prevent lag
            query = text("SELECT * FROM employees LIMIT 50")
            with self.engine.begin() as conn:
                employees_df = pd.read_sql(query, conn)
            
            if employees_df.empty:
                return {'processed_count': 0, 'total_gross': 0, 'total_deductions': 0, 'total_net': 0}
            
            total_gross = 0
            total_deductions = 0
            total_net = 0
            processed_count = 0
            
            # Process all employees in a single transaction
            with self.engine.begin() as conn:
                for _, employee in employees_df.iterrows():
                    # Generate random overtime and bonus for simulation
                    overtime_hours = np.random.randint(0, 20)  # 0-20 hours
                    bonus = np.random.randint(0, 5000) if np.random.random() > 0.7 else 0  # 30% chance of bonus
                    loan_deduction = np.random.randint(0, 2000) if np.random.random() > 0.8 else 0  # 20% chance of loan
                    
                    # Calculate payroll
                    payroll_data = self.calculate_payroll(
                        base_salary=employee['base_salary'],
                        overtime_hours=overtime_hours,
                        bonus=bonus,
                        loan_deduction=loan_deduction
                    )
                    
                    # Insert payroll record
                    insert_query = text("""
                        INSERT OR REPLACE INTO payroll_records 
                        (employee_id, year_month, base_salary, overtime_hours, overtime_pay, 
                         bonus, pf, tax, insurance, loan_deduction, gross_salary, 
                         total_deductions, net_salary, created_at)
                        VALUES (:employee_id, :year_month, :base_salary, :overtime_hours, :overtime_pay,
                                :bonus, :pf, :tax, :insurance, :loan_deduction, :gross_salary,
                                :total_deductions, :net_salary, :created_at)
                    """)
                    
                    conn.execute(insert_query, {
                        'employee_id': employee['employee_id'],
                        'year_month': year_month,
                        'base_salary': payroll_data['base_salary'],
                        'overtime_hours': payroll_data['overtime_hours'],
                        'overtime_pay': payroll_data['overtime_pay'],
                        'bonus': payroll_data['bonus'],
                        'pf': payroll_data['pf'],
                        'tax': payroll_data['tax'],
                        'insurance': payroll_data['insurance'],
                        'loan_deduction': payroll_data['loan_deduction'],
                        'gross_salary': payroll_data['gross_salary'],
                        'total_deductions': payroll_data['total_deductions'],
                        'net_salary': payroll_data['net_salary'],
                        'created_at': datetime.now()
                    })
                    
                    total_gross += payroll_data['gross_salary']
                    total_deductions += payroll_data['total_deductions']
                    total_net += payroll_data['net_salary']
                    processed_count += 1
            
            logger.info(f"Processed payroll for {processed_count} employees for {year_month}")
            
            return {
                'processed_count': processed_count,
                'total_gross': total_gross,
                'total_deductions': total_deductions,
                'total_net': total_net
            }
            
        except Exception as e:
            logger.error(f"Error processing monthly payroll: {str(e)}")
            raise
    
    def import_employees_from_csv(self, csv_path):
        """
        Import employees from CSV file
        """
        try:
            df = pd.read_csv(csv_path)
            
            # Standardize column names
            column_mapping = {
                'Employee_ID': 'employee_id',
                'Employee_Name': 'name',
                'Department': 'department',
                'Position': 'position',
                'Salary': 'base_salary',
                'Joining_Date': 'joining_date',
                'Email': 'email'
            }
            
            df = df.rename(columns=column_mapping)
            
            # Ensure required columns exist
            required_columns = ['employee_id', 'name', 'department', 'position', 'base_salary']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")
            
            # Fill missing optional columns
            if 'email' not in df.columns:
                df['email'] = df['employee_id'].apply(lambda x: f"emp{x}@company.com")
            
            if 'joining_date' not in df.columns:
                df['joining_date'] = '2020-01-01'
            
            imported_count = 0
            updated_count = 0
            
            for _, row in df.iterrows():
                # Check if employee exists
                check_query = text("SELECT id FROM employees WHERE employee_id = :employee_id")
                with self.engine.begin() as conn:
                    existing = conn.execute(check_query, {"employee_id": row['employee_id']}).fetchone()
                
                if existing:
                    # Update existing employee
                    update_query = text("""
                        UPDATE employees 
                        SET name = :name, department = :department, position = :position,
                            base_salary = :base_salary, email = :email, joining_date = :joining_date
                        WHERE employee_id = :employee_id
                    """)
                    with self.engine.begin() as conn:
                        conn.execute(update_query, {
                            'employee_id': row['employee_id'],
                            'name': row['name'],
                            'department': row['department'],
                            'position': row['position'],
                            'base_salary': row['base_salary'],
                            'email': row['email'],
                            'joining_date': row['joining_date']
                        })
                    updated_count += 1
                else:
                    # Insert new employee
                    insert_query = text("""
                        INSERT INTO employees 
                        (employee_id, name, email, department, position, base_salary, joining_date)
                        VALUES (:employee_id, :name, :email, :department, :position, :base_salary, :joining_date)
                    """)
                    with self.engine.begin() as conn:
                        conn.execute(insert_query, {
                            'employee_id': row['employee_id'],
                            'name': row['name'],
                            'email': row['email'],
                            'department': row['department'],
                            'position': row['position'],
                            'base_salary': row['base_salary'],
                            'joining_date': row['joining_date']
                        })
                    imported_count += 1
            
            logger.info(f"Imported {imported_count} new employees, updated {updated_count} existing employees")
            
            return {
                'imported_count': imported_count,
                'updated_count': updated_count
            }
            
        except Exception as e:
            logger.error(f"Error importing employees from CSV: {str(e)}")
            raise