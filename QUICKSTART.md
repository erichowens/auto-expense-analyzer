# 🚀 Quick Start Guide - Travel Expense Analyzer

## Prerequisites

1. **Python 3.8+** installed
2. **pip** package manager
3. **Chrome browser** (for hotel folio retrieval)

## 🎯 Step 1: Install Dependencies

```bash
# Install required packages
pip install -r requirements.txt
```

## 🎯 Step 2: Set Up Environment

Create a `.env` file with your credentials:

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your credentials
```

Required credentials:
- **Plaid** (optional): For automatic bank transaction import
- **Concur** (optional): For expense report submission

## 🎯 Step 3: Start the Application

```bash
# Run the Flask app
python expense_web_app.py
```

The app will start at: **http://localhost:5000**

## 🎯 Step 4: Using the Friday Panic Button

### Option A: Quick Processing (Last 30 Days)
1. Open http://localhost:5000
2. Click the **FRIDAY PANIC** button
3. Select **"Process Last 30 Days"**
4. Watch as all expenses are auto-categorized!

### Option B: Bulk Processing (Since Jan 2024)
1. Click the **FRIDAY PANIC** button
2. Select **"Process ALL Since Jan 2024"**
3. Processing runs in background
4. Check progress in the status bar

### Option C: Upload CSV Files
1. Export your Chase statements as CSV
2. Click **"Upload CSV Files"**
3. Select your files
4. Click **"Analyze"**

## 🎯 Step 5: Review Results

After processing:
- ✅ All transactions categorized (AIRFARE, HOTEL, MEALS, etc.)
- ✅ Business purposes auto-generated
- ✅ Trips grouped by date
- ✅ Ready for Concur submission

## 📊 Dashboard Features

- **Quick Actions**: One-click processing
- **Trip Summary**: View all business trips
- **Expense Breakdown**: See spending by category
- **Business Purpose**: Auto-generated descriptions
- **Export**: Download reports as CSV/PDF

## 🔥 Friday Panic Button Features

The magic button that saves your Friday:
- **Auto-categorizes** all expenses with 95%+ accuracy
- **Generates business purposes** based on patterns
- **Groups expenses** into logical trips
- **Flags items** needing review
- **Estimates time saved** (usually 20-30 minutes!)

## ⚙️ Configuration (Optional)

Edit `config.py` or set environment variables:

```bash
# Processing settings
export DEFAULT_START_DATE="2024-01-01"
export BATCH_SIZE=100
export CONFIDENCE_THRESHOLD=0.7

# Rate limits (for API protection)
export RATE_LIMIT_PANIC_BUTTON="10 per hour"
export RATE_LIMIT_BULK="5 per hour"
```

## 🚨 Troubleshooting

### Database Issues
```bash
# Reset database
rm data/expenses.db
python -c "from database_pool import get_db; get_db()"
```

### Import Issues
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

### Port Already in Use
```bash
# Use a different port
python expense_web_app.py --port 5001
```

## 📝 Sample Workflow

1. **Monday Morning**: Upload weekend receipts
2. **Throughout Week**: System auto-categorizes expenses
3. **Friday Afternoon**: Hit PANIC button to process everything
4. **Review**: Quick check of flagged items
5. **Submit**: One-click to Concur

## 🎉 You're Ready!

Open http://localhost:5000 and start processing expenses!

---

**Need Help?**
- Check the logs: `tail -f app.log`
- Review improvements: See `IMPROVEMENTS_SUMMARY.md`
- Run tests: `python test_improvements.py`