# Chase Travel Expense Analyzer

Analyzes Chase bank statements to identify travel expenses outside Oregon and groups them into trips for Concur expense reporting.

## Features

- **Plaid API Integration**: Automatically fetch transactions from Chase accounts
- **CSV Support**: Process downloaded Chase CSV statements
- **Location Detection**: Identifies non-Oregon expenses using merchant location data
- **Trip Grouping**: Groups contiguous expenses into logical trips
- **Expense Categorization**: Categorizes expenses (Hotel, Airfare, Meals, Transportation)
- **Concur-Ready Reports**: Generates formatted summaries for expense reporting

## Quick Start

### Option 1: Using Plaid API (Recommended)

1. **Setup Plaid**:
   ```bash
   python chase_travel_expense_analyzer.py --setup-plaid
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials**:
   ```bash
   cp .env.example .env
   # Edit .env with your Plaid credentials
   ```

4. **Run with Plaid**:
   ```bash
   python chase_travel_expense_analyzer.py --plaid --access-token YOUR_TOKEN
   ```

### Option 2: Using CSV Files

1. Download CSV statements from Chase online banking
2. Run the analyzer:
   ```bash
   python chase_travel_expense_analyzer.py --files statement1.csv statement2.csv
   ```

## Usage Examples

```bash
# Analyze last 2 years via Plaid
python chase_travel_expense_analyzer.py --plaid --access-token your_token

# Analyze CSV files for last 3 years
python chase_travel_expense_analyzer.py --files *.csv --years 3

# Save report to file
python chase_travel_expense_analyzer.py --plaid --access-token your_token --output report.txt

# Custom trip grouping (5 day gaps)
python chase_travel_expense_analyzer.py --files *.csv --gap-days 5
```

## Command Line Options

- `--plaid`: Use Plaid API instead of CSV files
- `--access-token`: Plaid access token for API access
- `--public-token`: Exchange public token for access token
- `--files`: CSV statement files to process
- `--years`: Number of years to analyze (default: 2)
- `--gap-days`: Max days between transactions in same trip (default: 2)
- `--output`: Save report to file
- `--setup-plaid`: Show Plaid setup instructions

## Sample Output

```
TRAVEL EXPENSE SUMMARY FOR CONCUR REPORTING
===========================================

Total Travel Expenses: $1,245.67
Number of Trips: 3

TRIP #1
-------
Dates: 01/15/2024 - 01/18/2024 (4 days)
Location: SEATTLE WA
Total Amount: $737.22

Expense Breakdown:
  HOTEL: $245.67
  AIRFARE: $425.00
  MEALS: $49.05
  TRANSPORTATION: $18.50
```

## Requirements

- Python 3.7+
- Plaid developer account (for API access)
- Chase bank account with transaction history

## Security

- Never commit your `.env` file
- Store API credentials securely
- Use sandbox environment for testing