#!/usr/bin/env python3
"""
Per Diem Tracking Module
Tracks daily meal expenses against configurable per diem allowances.
"""

from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import json
from flask import request, session, jsonify, render_template
from security_fixes import (
    SecureDatabase, InputValidator, require_csrf, require_session,
    rate_limit, SQLQueryBuilder
)


class PerDiemConfig:
    """Configuration for per diem allowances."""
    
    def __init__(self, daily_allowance: float = 75.00):
        self.daily_allowance = daily_allowance
        # Meal breakdowns (can be customized)
        self.breakfast_percentage = 0.20  # 20% = $15
        self.lunch_percentage = 0.35      # 35% = $26.25
        self.dinner_percentage = 0.45     # 45% = $33.75
        
        self.breakfast_allowance = daily_allowance * self.breakfast_percentage
        self.lunch_allowance = daily_allowance * self.lunch_percentage
        self.dinner_allowance = daily_allowance * self.dinner_percentage
        
        # Time windows for meal categorization
        self.meal_windows = {
            'breakfast': (5, 11),   # 5am - 11am
            'lunch': (11, 16),      # 11am - 4pm
            'dinner': (16, 22),     # 4pm - 10pm
        }


class PerDiemAnalyzer:
    """Analyzes expenses against per diem allowances."""
    
    def __init__(self, config: PerDiemConfig = None):
        self.config = config or PerDiemConfig()
        
    def categorize_meal_by_time(self, transaction_time: str) -> str:
        """Categorize a meal based on transaction time."""
        try:
            # Handle various time formats
            if ':' in transaction_time:
                hour = int(transaction_time.split(':')[0])
            else:
                hour = 12  # Default to lunch if time format is unclear
        except:
            hour = 12
            
        for meal, (start, end) in self.config.meal_windows.items():
            if start <= hour < end:
                return meal
        
        # Late night (10pm-5am) defaults to dinner
        return 'dinner'
    
    def categorize_meal_by_description(self, description: str) -> Optional[str]:
        """Try to categorize meal by description keywords."""
        desc_lower = description.lower()
        
        breakfast_keywords = ['breakfast', 'morning', 'coffee', 'bagel', 'donut', 
                            'starbucks', 'dunkin', 'pancake', 'waffle']
        lunch_keywords = ['lunch', 'noon', 'midday', 'sandwich', 'salad']
        dinner_keywords = ['dinner', 'evening', 'night', 'supper']
        
        if any(keyword in desc_lower for keyword in breakfast_keywords):
            return 'breakfast'
        elif any(keyword in desc_lower for keyword in lunch_keywords):
            return 'lunch'
        elif any(keyword in desc_lower for keyword in dinner_keywords):
            return 'dinner'
        
        return None
    
    def analyze_trip_expenses(self, expenses: List[Dict], 
                             start_date: str = None, 
                             end_date: str = None) -> Dict:
        """
        Analyze trip expenses against per diem allowances.
        
        Args:
            expenses: List of expense dictionaries
            start_date: Start date for analysis (YYYY-MM-DD)
            end_date: End date for analysis (YYYY-MM-DD)
            
        Returns:
            Dictionary with daily analysis and summary
        """
        # Filter expenses by date range if provided
        if start_date:
            expenses = [e for e in expenses if e.get('date', '') >= start_date]
        if end_date:
            expenses = [e for e in expenses if e.get('date', '') <= end_date]
        
        # Group expenses by date
        daily_expenses = defaultdict(lambda: {
            'breakfast': [], 'lunch': [], 'dinner': [], 'other': [],
            'total': 0.0, 'meal_total': 0.0
        })
        
        for expense in expenses:
            expense_date = expense.get('date', '')
            category = expense.get('category', '')
            amount = float(expense.get('amount', 0))
            description = expense.get('description', '')
            time = expense.get('time', '')
            
            # Only track meal expenses for per diem
            if category in ['MEALS', 'FOOD', 'RESTAURANT']:
                # Try to categorize the meal
                meal_type = self.categorize_meal_by_description(description)
                if not meal_type and time:
                    meal_type = self.categorize_meal_by_time(time)
                if not meal_type:
                    meal_type = 'other'
                
                daily_expenses[expense_date][meal_type].append({
                    'amount': amount,
                    'description': description,
                    'time': time
                })
                daily_expenses[expense_date]['meal_total'] += amount
            
            daily_expenses[expense_date]['total'] += amount
        
        # Calculate per diem compliance
        analysis = {
            'config': {
                'daily_allowance': self.config.daily_allowance,
                'breakfast_allowance': self.config.breakfast_allowance,
                'lunch_allowance': self.config.lunch_allowance,
                'dinner_allowance': self.config.dinner_allowance
            },
            'daily_analysis': {},
            'summary': {
                'total_days': 0,
                'days_under_limit': 0,
                'days_over_limit': 0,
                'days_at_limit': 0,
                'total_meal_expenses': 0.0,
                'total_allowance': 0.0,
                'total_saved': 0.0,
                'total_overage': 0.0,
                'compliance_rate': 0.0
            }
        }
        
        # Analyze each day
        for date_str in sorted(daily_expenses.keys()):
            if not date_str:  # Skip empty dates
                continue
                
            day_data = daily_expenses[date_str]
            
            # Calculate meal totals
            breakfast_total = sum(e['amount'] for e in day_data['breakfast'])
            lunch_total = sum(e['amount'] for e in day_data['lunch'])
            dinner_total = sum(e['amount'] for e in day_data['dinner'])
            other_total = sum(e['amount'] for e in day_data['other'])
            
            # Calculate differences
            daily_diff = self.config.daily_allowance - day_data['meal_total']
            
            day_analysis = {
                'date': date_str,
                'meals': {
                    'breakfast': {
                        'expenses': day_data['breakfast'],
                        'total': breakfast_total,
                        'allowance': self.config.breakfast_allowance,
                        'difference': self.config.breakfast_allowance - breakfast_total,
                        'within_limit': breakfast_total <= self.config.breakfast_allowance
                    },
                    'lunch': {
                        'expenses': day_data['lunch'],
                        'total': lunch_total,
                        'allowance': self.config.lunch_allowance,
                        'difference': self.config.lunch_allowance - lunch_total,
                        'within_limit': lunch_total <= self.config.lunch_allowance
                    },
                    'dinner': {
                        'expenses': day_data['dinner'],
                        'total': dinner_total,
                        'allowance': self.config.dinner_allowance,
                        'difference': self.config.dinner_allowance - dinner_total,
                        'within_limit': dinner_total <= self.config.dinner_allowance
                    },
                    'other': {
                        'expenses': day_data['other'],
                        'total': other_total
                    }
                },
                'daily_meal_total': day_data['meal_total'],
                'daily_allowance': self.config.daily_allowance,
                'difference': daily_diff,
                'within_limit': daily_diff >= 0,
                'savings_or_overage': abs(daily_diff)
            }
            
            analysis['daily_analysis'][date_str] = day_analysis
            
            # Update summary
            analysis['summary']['total_days'] += 1
            analysis['summary']['total_meal_expenses'] += day_data['meal_total']
            analysis['summary']['total_allowance'] += self.config.daily_allowance
            
            if daily_diff > 0.01:  # Under limit (with small epsilon for float comparison)
                analysis['summary']['days_under_limit'] += 1
                analysis['summary']['total_saved'] += daily_diff
            elif daily_diff < -0.01:  # Over limit
                analysis['summary']['days_over_limit'] += 1
                analysis['summary']['total_overage'] += abs(daily_diff)
            else:  # Exactly at limit
                analysis['summary']['days_at_limit'] += 1
        
        # Calculate compliance rate
        if analysis['summary']['total_days'] > 0:
            analysis['summary']['compliance_rate'] = (
                (analysis['summary']['days_under_limit'] + analysis['summary']['days_at_limit']) 
                / analysis['summary']['total_days'] * 100
            )
        
        return analysis
    
    def generate_report(self, analysis: Dict, format: str = 'text') -> str:
        """
        Generate a formatted per diem report.
        
        Args:
            analysis: Analysis dictionary from analyze_trip_expenses
            format: Output format ('text', 'html', 'json')
            
        Returns:
            Formatted report string
        """
        if format == 'json':
            return json.dumps(analysis, indent=2)
        
        elif format == 'html':
            return self._generate_html_report(analysis)
        
        else:  # text format
            return self._generate_text_report(analysis)
    
    def _generate_text_report(self, analysis: Dict) -> str:
        """Generate text format report."""
        lines = []
        lines.append("=" * 70)
        lines.append("PER DIEM EXPENSE ANALYSIS REPORT")
        lines.append("=" * 70)
        
        config = analysis['config']
        lines.append(f"\nDaily Allowances:")
        lines.append(f"  Total: ${config['daily_allowance']:.2f}")
        lines.append(f"  - Breakfast: ${config['breakfast_allowance']:.2f} (20%)")
        lines.append(f"  - Lunch: ${config['lunch_allowance']:.2f} (35%)")
        lines.append(f"  - Dinner: ${config['dinner_allowance']:.2f} (45%)")
        
        summary = analysis['summary']
        lines.append(f"\n" + "=" * 70)
        lines.append("SUMMARY")
        lines.append("-" * 70)
        lines.append(f"Total Days Analyzed: {summary['total_days']}")
        lines.append(f"Compliance Rate: {summary['compliance_rate']:.1f}%")
        lines.append("")
        lines.append(f"Days Under Limit: {summary['days_under_limit']} ✅")
        lines.append(f"Days At Limit: {summary['days_at_limit']} ✓")
        lines.append(f"Days Over Limit: {summary['days_over_limit']} ⚠️")
        lines.append("")
        lines.append(f"Total Meal Expenses: ${summary['total_meal_expenses']:.2f}")
        lines.append(f"Total Allowance: ${summary['total_allowance']:.2f}")
        lines.append(f"Total Saved: ${summary['total_saved']:.2f} 💰")
        lines.append(f"Total Overage: ${summary['total_overage']:.2f} 📈")
        
        lines.append(f"\n" + "=" * 70)
        lines.append("DAILY BREAKDOWN")
        lines.append("-" * 70)
        
        for date_str in sorted(analysis['daily_analysis'].keys()):
            day = analysis['daily_analysis'][date_str]
            status = "✅" if day['within_limit'] else "❌"
            
            lines.append(f"\n{date_str} {status}")
            lines.append(f"  Daily Total: ${day['daily_meal_total']:.2f} / ${day['daily_allowance']:.2f}")
            lines.append(f"  Difference: ${day['difference']:+.2f}")
            
            meals = day['meals']
            if meals['breakfast']['total'] > 0:
                b_status = "✓" if meals['breakfast']['within_limit'] else "✗"
                lines.append(f"  Breakfast {b_status}: ${meals['breakfast']['total']:.2f} / ${meals['breakfast']['allowance']:.2f}")
                for expense in meals['breakfast']['expenses'][:2]:  # Show first 2
                    lines.append(f"    - {expense['description']}: ${expense['amount']:.2f}")
            
            if meals['lunch']['total'] > 0:
                l_status = "✓" if meals['lunch']['within_limit'] else "✗"
                lines.append(f"  Lunch {l_status}: ${meals['lunch']['total']:.2f} / ${meals['lunch']['allowance']:.2f}")
                for expense in meals['lunch']['expenses'][:2]:
                    lines.append(f"    - {expense['description']}: ${expense['amount']:.2f}")
            
            if meals['dinner']['total'] > 0:
                d_status = "✓" if meals['dinner']['within_limit'] else "✗"
                lines.append(f"  Dinner {d_status}: ${meals['dinner']['total']:.2f} / ${meals['dinner']['allowance']:.2f}")
                for expense in meals['dinner']['expenses'][:2]:
                    lines.append(f"    - {expense['description']}: ${expense['amount']:.2f}")
            
            if meals['other']['total'] > 0:
                lines.append(f"  Other Meals: ${meals['other']['total']:.2f}")
        
        lines.append("\n" + "=" * 70)
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 70)
        
        if summary['compliance_rate'] >= 90:
            lines.append("✅ Excellent per diem compliance! Keep up the good work.")
        elif summary['compliance_rate'] >= 70:
            lines.append("⚠️ Good compliance, but there's room for improvement.")
            if summary['days_over_limit'] > 0:
                lines.append("   Consider planning meals in advance for better budget control.")
        else:
            lines.append("❌ Low per diem compliance. Consider these tips:")
            lines.append("   - Plan meals in advance")
            lines.append("   - Look for more affordable dining options")
            lines.append("   - Consider meal prep or grocery shopping")
        
        if summary['total_saved'] > 100:
            lines.append(f"\n💰 Great job! You saved ${summary['total_saved']:.2f} on this trip.")
        
        lines.append("\n" + "=" * 70)
        
        return "\n".join(lines)
    
    def _generate_html_report(self, analysis: Dict) -> str:
        """Generate HTML format report."""
        summary = analysis['summary']
        config = analysis['config']
        
        html = f"""
        <div class="per-diem-report">
            <h2>Per Diem Expense Analysis</h2>
            
            <div class="summary-cards">
                <div class="card">
                    <h3>Compliance Rate</h3>
                    <div class="big-number">{summary['compliance_rate']:.1f}%</div>
                </div>
                <div class="card">
                    <h3>Total Saved</h3>
                    <div class="big-number positive">${summary['total_saved']:.2f}</div>
                </div>
                <div class="card">
                    <h3>Total Overage</h3>
                    <div class="big-number negative">${summary['total_overage']:.2f}</div>
                </div>
            </div>
            
            <div class="daily-breakdown">
                <h3>Daily Breakdown</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Breakfast</th>
                            <th>Lunch</th>
                            <th>Dinner</th>
                            <th>Total</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for date_str in sorted(analysis['daily_analysis'].keys()):
            day = analysis['daily_analysis'][date_str]
            status_class = "success" if day['within_limit'] else "danger"
            status_icon = "✅" if day['within_limit'] else "❌"
            
            html += f"""
                <tr class="{status_class}">
                    <td>{date_str}</td>
                    <td>${day['meals']['breakfast']['total']:.2f}</td>
                    <td>${day['meals']['lunch']['total']:.2f}</td>
                    <td>${day['meals']['dinner']['total']:.2f}</td>
                    <td>${day['daily_meal_total']:.2f} / ${config['daily_allowance']:.2f}</td>
                    <td>{status_icon}</td>
                </tr>
            """
        
        html += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <style>
            .per-diem-report { font-family: Arial, sans-serif; }
            .summary-cards { display: flex; gap: 20px; margin: 20px 0; }
            .card { flex: 1; padding: 20px; background: #f5f5f5; border-radius: 8px; text-align: center; }
            .big-number { font-size: 2em; font-weight: bold; margin-top: 10px; }
            .positive { color: green; }
            .negative { color: red; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
            .success { background-color: #d4edda; }
            .danger { background-color: #f8d7da; }
        </style>
        """
        
        return html


# Integration function for expense_web_app.py
def add_per_diem_routes(app, db_path='expense_tracker.db'):
    """Add per diem tracking routes to Flask app with security."""
    
    @app.route('/api/per-diem/config', methods=['GET', 'POST'])
    @require_session
    @rate_limit(max_attempts=30, window_minutes=1)
    def per_diem_config():
        """Get or update per diem configuration."""
        if request.method == 'GET':
            # Get current config from session or database
            config = session.get('per_diem_config', {
                'daily_allowance': 75.00,
                'breakfast_percentage': 0.20,
                'lunch_percentage': 0.35,
                'dinner_percentage': 0.45
            })
            return jsonify(config)
        
        else:  # POST
            # Require CSRF token for POST
            from security_fixes import CSRFProtection
            token = CSRFProtection.get_token_from_request()
            if not CSRFProtection.validate_token(token):
                return jsonify({'error': 'Invalid CSRF token'}), 403
            
            data = request.get_json()
            
            # Validate input values
            try:
                daily_allowance = InputValidator.validate_amount(
                    data.get('daily_allowance', 75.00),
                    min_val=0,
                    max_val=1000
                )
                breakfast_pct = float(data.get('breakfast_percentage', 0.20))
                lunch_pct = float(data.get('lunch_percentage', 0.35))
                dinner_pct = float(data.get('dinner_percentage', 0.45))
                
                # Validate percentages
                if not (0 <= breakfast_pct <= 1 and 0 <= lunch_pct <= 1 and 0 <= dinner_pct <= 1):
                    raise ValueError("Percentages must be between 0 and 1")
                
                if abs((breakfast_pct + lunch_pct + dinner_pct) - 1.0) > 0.01:
                    raise ValueError("Meal percentages must sum to 100%")
                    
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            
            config = {
                'daily_allowance': daily_allowance,
                'breakfast_percentage': breakfast_pct,
                'lunch_percentage': lunch_pct,
                'dinner_percentage': dinner_pct
            }
            session['per_diem_config'] = config
            return jsonify({'success': True, 'config': config})
    
    @app.route('/api/per-diem/analyze', methods=['POST'])
    @require_csrf
    @require_session
    @rate_limit(max_attempts=10, window_minutes=1)
    def analyze_per_diem():
        """Analyze expenses against per diem allowances with validation."""
        data = request.get_json()
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        # Validate and get configuration
        try:
            daily_allowance = InputValidator.validate_amount(
                data.get('daily_allowance', 75.00),
                min_val=0,
                max_val=1000
            )
            
            # Validate dates if provided
            start_date = None
            end_date = None
            
            if data.get('start_date'):
                start_date = InputValidator.validate_date(data['start_date'])
                start_date = start_date.strftime('%Y-%m-%d')
            
            if data.get('end_date'):
                end_date = InputValidator.validate_date(data['end_date'])
                end_date = end_date.strftime('%Y-%m-%d')
            
            if start_date and end_date:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                if end_dt < start_dt:
                    raise ValueError("End date must be after start date")
                if (end_dt - start_dt).days > 365:
                    raise ValueError("Date range cannot exceed 365 days")
                    
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # Get expenses from database securely
        with SecureDatabase(db_path) as db:
            # Build secure query
            where_conditions = {
                'user_id': user_id
            }
            
            # Use parameterized query for complex conditions
            query = """
                SELECT date, category, amount, description, 
                       time(datetime) as time
                FROM transactions
                WHERE user_id = ? 
                  AND category IN ('MEALS', 'FOOD', 'RESTAURANT')
            """
            params = [user_id]
            
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            
            query += " ORDER BY date, time LIMIT 10000"  # Prevent excessive data retrieval
            
            cursor = db.execute(query, params)
            expenses = [
                {
                    'date': row[0],
                    'category': row[1],
                    'amount': row[2],
                    'description': row[3],
                    'time': row[4]
                }
                for row in cursor.fetchall()
            ]
        
        # Analyze expenses
        config = PerDiemConfig(daily_allowance)
        analyzer = PerDiemAnalyzer(config)
        analysis = analyzer.analyze_trip_expenses(expenses, start_date, end_date)
        
        # Generate report
        text_report = analyzer.generate_report(analysis, 'text')
        html_report = analyzer.generate_report(analysis, 'html')
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'text_report': text_report,
            'html_report': html_report
        })
    
    @app.route('/per-diem')
    @require_session
    def per_diem_dashboard():
        """Per diem tracking dashboard with session validation."""
        from flask_wtf.csrf import generate_csrf
        csrf_token = generate_csrf()
        return render_template('per_diem.html', csrf_token=csrf_token)
    
    return app


if __name__ == '__main__':
    # Test the per diem analyzer
    print("Testing Per Diem Analyzer...")
    
    # Sample expenses
    test_expenses = [
        {'date': '2024-11-20', 'category': 'MEALS', 'amount': 12.50, 
         'time': '08:30', 'description': 'Starbucks Coffee'},
        {'date': '2024-11-20', 'category': 'MEALS', 'amount': 28.75, 
         'time': '12:45', 'description': 'Business Lunch at Chipotle'},
        {'date': '2024-11-20', 'category': 'MEALS', 'amount': 45.00, 
         'time': '19:00', 'description': 'Team Dinner'},
        {'date': '2024-11-21', 'category': 'MEALS', 'amount': 8.50, 
         'time': '09:00', 'description': 'Breakfast'},
        {'date': '2024-11-21', 'category': 'MEALS', 'amount': 22.00, 
         'time': '13:00', 'description': 'Lunch Meeting'},
        {'date': '2024-11-21', 'category': 'MEALS', 'amount': 38.00, 
         'time': '18:30', 'description': 'Client Dinner'},
    ]
    
    analyzer = PerDiemAnalyzer()
    analysis = analyzer.analyze_trip_expenses(test_expenses)
    report = analyzer.generate_report(analysis, 'text')
    
    print(report)
    print("\n✅ Per Diem Analyzer test complete!")