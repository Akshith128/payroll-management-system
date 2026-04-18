"""
Payroll forecasting module using Linear Regression
Forecasts future payroll costs by department and month
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PayrollForecaster:
    def __init__(self, engine):
        self.engine = engine
        self.models = {}
    
    def prepare_time_series_data(self, department=None):
        """
        Prepare time series data for forecasting
        """
        try:
            # Build query based on department filter
            if department:
                query = text("""
                    SELECT 
                        pr.year_month,
                        e.department,
                        SUM(pr.gross_salary) as total_gross,
                        COUNT(*) as employee_count,
                        AVG(pr.gross_salary) as avg_gross
                    FROM payroll_records pr
                    JOIN employees e ON pr.employee_id = e.employee_id
                    WHERE e.department = :department
                    GROUP BY pr.year_month, e.department
                    ORDER BY pr.year_month
                """)
                params = {'department': department}
            else:
                query = text("""
                    SELECT 
                        pr.year_month,
                        e.department,
                        SUM(pr.gross_salary) as total_gross,
                        COUNT(*) as employee_count,
                        AVG(pr.gross_salary) as avg_gross
                    FROM payroll_records pr
                    JOIN employees e ON pr.employee_id = e.employee_id
                    GROUP BY pr.year_month, e.department
                    ORDER BY pr.year_month, e.department
                """)
                params = {}
            
            with self.engine.begin() as conn:
                df = pd.read_sql(query, conn, params=params)
            
            if df.empty:
                return pd.DataFrame()
            
            # Convert year_month to datetime for time series analysis
            df['date'] = pd.to_datetime(df['year_month'] + '-01')
            df['month_num'] = df['date'].dt.month
            df['year'] = df['date'].dt.year
            
            # Create time index (months since start)
            start_date = df['date'].min()
            df['time_index'] = ((df['date'] - start_date).dt.days / 30.44).astype(int)
            
            return df
            
        except Exception as e:
            logger.error(f"Error preparing time series data: {str(e)}")
            return pd.DataFrame()
    
    def generate_forecasts(self, months_ahead=3, target_year: int | None = None, start_year_month: str | None = None):
        """
        Generate forecasts for all departments
        If start_year_month (YYYY-MM) is provided, generate for that month and next (months_ahead-1) months.
        """
        try:
            def add_months(d: datetime, i: int) -> datetime:
                m = d.month - 1 + i
                y = d.year + m // 12
                m2 = m % 12 + 1
                return datetime(y, m2, 1)

            # Normalize explicit start months if provided
            start_dt = None
            if start_year_month:
                try:
                    start_dt = datetime.strptime(start_year_month + '-01', '%Y-%m-%d')
                except Exception:
                    start_dt = None
            # Get all departments
            with self.engine.begin() as conn:
                dept_query = text("SELECT DISTINCT department FROM employees")
                departments = [row[0] for row in conn.execute(dept_query).fetchall() if row[0]]

            # Clear existing forecasts
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM forecasts"))

            total_forecasts = 0

            for department in departments:
                forecasts = self._forecast_department(department, months_ahead, target_year, start_dt)
                total_forecasts += len(forecasts)

                # Store forecasts in database
                with self.engine.begin() as conn:
                    insert_query = text(
                        """
                        INSERT INTO forecasts 
                        (department, year_month, predicted_gross, confidence_score)
                        VALUES (:department, :year_month, :predicted_gross, :confidence_score)
                        """
                    )
                    for forecast in forecasts:
                        conn.execute(insert_query, {
                            'department': department,
                            'year_month': forecast['year_month'],
                            'predicted_gross': float(forecast['predicted_gross']),
                            'confidence_score': float(forecast['confidence_score'])
                        })

            logger.info(f"Generated {total_forecasts} forecasts for {len(departments)} departments")

            # Fallback: if none generated, try using aggregated data to at least produce a baseline per department
            if total_forecasts == 0:
                with self.engine.begin() as conn:
                    df_all = pd.read_sql(text(
                        """
                        SELECT 
                            pr.year_month,
                            e.department,
                            SUM(pr.gross_salary) as total_gross
                        FROM payroll_records pr
                        JOIN employees e ON pr.employee_id = e.employee_id
                        GROUP BY pr.year_month, e.department
                        ORDER BY pr.year_month, e.department
                        """
                    ), conn)
                if not df_all.empty:
                    for dep in sorted(df_all['department'].dropna().unique()):
                        sub = df_all[df_all['department'] == dep].copy()
                        if sub.empty:
                            continue
                        sub = sub.sort_values('year_month')
                        baseline = float(sub['total_gross'].mean())
                        if start_dt is not None:
                            future_dates = [add_months(start_dt, i) for i in range(0, months_ahead)]
                        elif target_year:
                            # Default to first 3 months of target year when months_ahead=3
                            future_dates = [datetime(target_year, m, 1) for m in range(1, months_ahead + 1)]
                        else:
                            last_ym = pd.to_datetime(sub['year_month'].iloc[-1] + '-01')
                            future_dates = [add_months(last_ym, i) for i in range(1, months_ahead + 1)]
                        for future_date in future_dates:
                            with self.engine.begin() as conn:
                                conn.execute(text(
                                    """
                                    INSERT INTO forecasts (department, year_month, predicted_gross, confidence_score)
                                    VALUES (:d, :ym, :pg, :cs)
                                    """
                                ), {
                                    'd': dep,
                                    'ym': future_date.strftime('%Y-%m'),
                                    'pg': max(0.0, baseline),
                                    'cs': 0.25
                                })
                            total_forecasts += 1

            return total_forecasts

        except Exception as e:
            logger.error(f"Error generating forecasts: {str(e)}")
            raise
    
    def _forecast_department(self, department, months_ahead, target_year: int | None, start_dt: datetime | None):
        """
        Generate forecasts for a specific department
        """
        try:
            def add_months(d: datetime, i: int) -> datetime:
                m = d.month - 1 + i
                y = d.year + m // 12
                m2 = m % 12 + 1
                return datetime(y, m2, 1)
            # Get time series data for department
            df = self.prepare_time_series_data(department)
            
            if df.empty or len(df) < 3:
                # Not enough data for forecasting; fall back to baseline using latest or average
                if df.empty:
                    return []
                df = df.sort_values('date')
                last_date = df['date'].max()
                # Use average of available totals as baseline
                baseline = float(df['total_gross'].mean())
                forecasts = []
                if start_dt is not None:
                    future_dates = [add_months(start_dt, i) for i in range(0, months_ahead)]
                elif target_year:
                    future_dates = [datetime(target_year, m, 1) for m in range(1, months_ahead + 1)]
                else:
                    future_dates = [add_months(last_date, i) for i in range(1, months_ahead + 1)]
                for future_date in future_dates:
                    forecasts.append({
                        'year_month': future_date.strftime('%Y-%m'),
                        'predicted_gross': max(0.0, baseline),
                        'confidence_score': 0.3  # low confidence due to limited history
                    })
                self.models[department] = None
                return forecasts
            
            # Prepare features for regression
            X = df[['time_index', 'month_num']].values
            y = df['total_gross'].values
            
            # Train linear regression model
            model = LinearRegression()
            model.fit(X, y)
            
            # Generate predictions for future months (or entire target year)
            forecasts = []
            last_date = df['date'].max()
            if start_dt is not None:
                future_dates = [add_months(start_dt, i) for i in range(0, months_ahead)]
            elif target_year:
                future_dates = [datetime(target_year, m, 1) for m in range(1, months_ahead + 1)]
                # recompute time index for those dates
                start_date = df['date'].min()
                max_time_index = df['time_index'].max()
                # approximate months since start
                def time_index_for(date_val):
                    return int(((date_val - start_date).days) / 30.44)
                future_indices = [time_index_for(d) for d in future_dates]
                for fd, ti in zip(future_dates, future_indices):
                    pred = model.predict([[ti, fd.month]])[0]
                    y_pred = model.predict(X)
                    mse = np.mean((y - y_pred) ** 2)
                    confidence = max(0, min(1, 1 - (mse / np.var(y))))
                    forecasts.append({
                        'year_month': fd.strftime('%Y-%m'),
                        'predicted_gross': max(0, pred),
                        'confidence_score': confidence
                    })
            else:
                for i in range(1, months_ahead + 1):
                    future_date = add_months(last_date, i)
                    future_month = future_date.month
                    future_time_index = df['time_index'].max() + i
                
                    prediction = model.predict([[future_time_index, future_month]])[0]
                    y_pred = model.predict(X)
                    mse = np.mean((y - y_pred) ** 2)
                    confidence = max(0, min(1, 1 - (mse / np.var(y))))
                    forecasts.append({
                        'year_month': future_date.strftime('%Y-%m'),
                        'predicted_gross': max(0, prediction),
                        'confidence_score': confidence
                    })
            
            # Store model for this department
            self.models[department] = model
            
            return forecasts
            
        except Exception as e:
            logger.error(f"Error forecasting department {department}: {str(e)}")
            return []
    
    def get_forecast_accuracy(self, department=None):
        """
        Calculate forecast accuracy for historical data
        """
        try:
            if department:
                query = text(
                    """
                    SELECT 
                        f.year_month,
                        f.predicted_gross,
                        SUM(pr.gross_salary) as actual_gross
                    FROM forecasts f
                    LEFT JOIN payroll_records pr ON f.year_month = pr.year_month
                    LEFT JOIN employees e ON pr.employee_id = e.employee_id
                    WHERE f.department = :department
                    GROUP BY f.year_month, f.predicted_gross
                    ORDER BY f.year_month
                    """
                )
                params = {'department': department}
            else:
                query = text(
                    """
                    SELECT 
                        f.year_month,
                        f.department,
                        f.predicted_gross,
                        SUM(pr.gross_salary) as actual_gross
                    FROM forecasts f
                    LEFT JOIN payroll_records pr ON f.year_month = pr.year_month
                    LEFT JOIN employees e ON pr.employee_id = e.employee_id
                    WHERE f.department = e.department
                    GROUP BY f.year_month, f.department, f.predicted_gross
                    ORDER BY f.year_month, f.department
                    """
                )
                params = {}

            with self.engine.begin() as conn:
                df = pd.read_sql(query, conn, params=params)

            if df.empty:
                return {'accuracy': 0, 'mape': 0, 'rmse': 0}

            # Calculate accuracy metrics
            df = df.dropna()

            if len(df) == 0:
                return {'accuracy': 0, 'mape': 0, 'rmse': 0}

            # Mean Absolute Percentage Error
            mape = np.mean(np.abs((df['actual_gross'] - df['predicted_gross']) / df['actual_gross'])) * 100

            # Root Mean Square Error
            rmse = np.sqrt(np.mean((df['actual_gross'] - df['predicted_gross']) ** 2))

            # Accuracy (1 - MAPE)
            accuracy = max(0, 1 - (mape / 100))

            return {
                'accuracy': accuracy,
                'mape': mape,
                'rmse': rmse,
                'sample_size': len(df)
            }

        except Exception as e:
            logger.error(f"Error calculating forecast accuracy: {str(e)}")
            return {'accuracy': 0, 'mape': 0, 'rmse': 0}
    
    def get_trend_analysis(self, department=None):
        """
        Analyze payroll trends over time
        """
        try:
            df = self.prepare_time_series_data(department)
            
            if df.empty:
                return {'trend': 'stable', 'growth_rate': 0}
            
            # Calculate month-over-month growth
            df = df.sort_values('year_month')
            df['growth_rate'] = df['total_gross'].pct_change() * 100
            
            # Calculate average growth rate
            avg_growth = df['growth_rate'].mean()
            
            # Determine trend
            if avg_growth > 2:
                trend = 'increasing'
            elif avg_growth < -2:
                trend = 'decreasing'
            else:
                trend = 'stable'
            
            return {
                'trend': trend,
                'growth_rate': avg_growth,
                'volatility': df['growth_rate'].std(),
                'latest_month': df['year_month'].iloc[-1],
                'latest_amount': df['total_gross'].iloc[-1]
            }
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {str(e)}")
            return {'trend': 'stable', 'growth_rate': 0}