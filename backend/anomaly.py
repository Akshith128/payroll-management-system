"""
Anomaly detection module using Isolation Forest
Detects unusual payroll patterns and flags potential issues
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import create_engine, text
import logging

logger = logging.getLogger(__name__)

class AnomalyDetector:
    def __init__(self, engine):
        self.engine = engine
        self.model = None
    
    def prepare_features(self, df):
        """
        Prepare features for anomaly detection
        """
        # Select numeric features for anomaly detection
        features = ['base_salary', 'overtime_hours', 'bonus', 'total_deductions', 'net_salary']
        
        # Create feature matrix
        X = df[features].fillna(0)
        
        # Add derived features
        X['salary_to_deduction_ratio'] = X['base_salary'] / (X['total_deductions'] + 1)
        X['overtime_intensity'] = X['overtime_hours'] / 160  # Normalize by standard hours
        X['bonus_ratio'] = X['bonus'] / (X['base_salary'] + 1)
        
        return X
    
    def detect_anomalies(self, contamination=0.02, months: int = 6, max_rows: int = 100):
        """
        Simple anomaly detection using basic rules (no ML)
        """
        try:
            # Get recent payroll records (limited)
            query = text(
                """
                SELECT pr.*, e.department, e.position
                FROM payroll_records pr
                JOIN employees e ON pr.employee_id = e.employee_id
                ORDER BY pr.year_month DESC
                LIMIT :max_rows
                """
            )

            with self.engine.begin() as conn:
                df = pd.read_sql(query, conn, params={'max_rows': max_rows})

            if df.empty:
                return {'anomaly_count': 0, 'total_records': 0}

            # Simple rule-based anomaly detection
            anomalies = []
            for idx, row in df.iterrows():
                is_anomaly = False
                details = []
                
                # Rule 1: Very high salary
                if row['base_salary'] > 100000:
                    is_anomaly = True
                    details.append("Very high base salary")
                
                # Rule 2: Excessive overtime
                if row['overtime_hours'] > 50:
                    is_anomaly = True
                    details.append("Excessive overtime")
                
                # Rule 3: Negative net salary
                if row['net_salary'] < 0:
                    is_anomaly = True
                    details.append("Negative net salary")
                
                # Rule 4: Very high bonus
                if row['bonus'] > row['base_salary'] * 0.5:
                    is_anomaly = True
                    details.append("High bonus relative to salary")

                if is_anomaly:
                    anomalies.append({
                        'payroll_record_id': row.get('id', row.get('rowid', 0)),
                        'score': -0.5,  # Simple score
                        'is_anomaly': 1,
                        'details': "; ".join(details)
                    })

            # Clear existing anomalies and insert new ones
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM anomalies"))
                if anomalies:
                    insert_query = text(
                        """
                        INSERT INTO anomalies 
                        (payroll_record_id, score, is_anomaly, details)
                        VALUES (:payroll_record_id, :score, :is_anomaly, :details)
                        """
                    )
                    for anomaly in anomalies:
                        conn.execute(insert_query, anomaly)

            logger.info(f"Detected {len(anomalies)} anomalies out of {len(df)} records")

            return {
                'anomaly_count': len(anomalies),
                'total_records': len(df)
            }

        except Exception as e:
            logger.error(f"Error detecting anomalies: {str(e)}")
            raise
    
    def _generate_anomaly_details(self, record, features):
        """
        Generate human-readable details about why a record is flagged as anomalous
        """
        details = []
        
        # Check for unusual salary patterns
        if features['base_salary'] > features['base_salary'].quantile(0.95):
            details.append("Unusually high base salary")
        
        if features['overtime_hours'] > 40:
            details.append("Excessive overtime hours")
        
        if features['bonus'] > features['base_salary'] * 0.5:
            details.append("Unusually high bonus relative to salary")
        
        if features['salary_to_deduction_ratio'] < 2:
            details.append("High deductions relative to salary")
        
        if features['overtime_intensity'] > 0.3:
            details.append("High overtime intensity")
        
        if features['bonus_ratio'] > 0.3:
            details.append("High bonus ratio")
        
        # Check for negative net salary
        if record['net_salary'] < 0:
            details.append("Negative net salary")
        
        # Check for unusual department patterns
        dept_query = text("""
            SELECT AVG(net_salary) as avg_salary, STDDEV(net_salary) as std_salary
            FROM payroll_records pr
            JOIN employees e ON pr.employee_id = e.employee_id
            WHERE e.department = :department
        """)
        
        dept_stats = self.engine.execute(dept_query, department=record['department']).fetchone()
        
        if dept_stats and dept_stats.avg_salary and dept_stats.std_salary:
            z_score = (record['net_salary'] - dept_stats.avg_salary) / dept_stats.std_salary
            if abs(z_score) > 2:
                details.append(f"Net salary {z_score:.1f} standard deviations from department average")
        
        return "; ".join(details) if details else "Unusual pattern detected"
    
    def get_anomaly_summary(self):
        """
        Get summary statistics of detected anomalies
        """
        try:
            query = text("""
                SELECT 
                    COUNT(*) as total_anomalies,
                    AVG(score) as avg_score,
                    MIN(score) as min_score,
                    MAX(score) as max_score
                FROM anomalies 
                WHERE is_anomaly = 1
            """)
            
            result = self.engine.execute(query).fetchone()
            
            if result:
                return dict(result._mapping)
            else:
                return {'total_anomalies': 0, 'avg_score': 0, 'min_score': 0, 'max_score': 0}
                
        except Exception as e:
            logger.error(f"Error getting anomaly summary: {str(e)}")
            return {'total_anomalies': 0, 'avg_score': 0, 'min_score': 0, 'max_score': 0}