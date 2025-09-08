# 📧 Gmail OAuth Setup Guide

## Overview
This guide will help you set up Google OAuth to automatically fetch Concur trip emails from your Gmail account and track per diem expenses.

## 🚀 Quick Start (Demo Mode)

No setup required! The application works in demo mode without any credentials:

```bash
python oauth_enhanced.py
```

Open http://localhost:8080 and all features work with demo data.

## 🔐 Production Setup

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Create Project" or select an existing project
3. Give it a name like "Travel Expense Analyzer"

### Step 2: Enable Gmail API

1. In your project, go to **APIs & Services** > **Library**
2. Search for "Gmail API"
3. Click on it and press **Enable**

### Step 3: Create OAuth Credentials

1. Go to **APIs & Services** > **Credentials**
2. Click **+ CREATE CREDENTIALS** > **OAuth client ID**
3. If prompted, configure the OAuth consent screen first:
   - User Type: **Internal** (for company) or **External** (for personal)
   - App name: "Travel Expense Analyzer"
   - User support email: Your email
   - Developer contact: Your email

4. For Application type, select **Web application**
5. Name: "Travel Expense OAuth"
6. Add authorized redirect URIs:
   ```
   http://localhost:8080/auth/google/callback
   ```

7. Click **Create**
8. Download the credentials JSON or copy the Client ID and Secret

### Step 4: Configure Environment

Add to your `.env` file:

```bash
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret_here

# Optional: Override default per diem
DAILY_FOOD_ALLOWANCE=75.00
```

### Step 5: Install Dependencies

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

Or update requirements.txt and run:
```bash
pip install -r requirements.txt
```

## 📱 Using Gmail Integration

### Connect Gmail Account

1. Open http://localhost:8080
2. Click **"Connect Gmail"** button
3. Sign in with your Google account
4. Grant permission to read emails
5. You're connected!

### What It Does

The Gmail integration will:
- ✅ Search for emails from Concur (@concursolutions.com, @concur.com)
- ✅ Extract trip information (destinations, dates, approval status)
- ✅ Identify expense report IDs
- ✅ Show trip timeline for expense correlation

### Email Patterns Detected

The system looks for:
- "Your expense report ... has been approved"
- "Trip to [destination] from [date] to [date]"
- "Business trip: [location] ([dates])"
- "Expense report submitted for [destination] trip"
- Report IDs and approval status

## 💰 Per Diem Tracking

### Setting Daily Allowances

The default is $75/day, broken down as:
- **Breakfast**: 20% ($15.00)
- **Lunch**: 35% ($26.25)  
- **Dinner**: 45% ($33.75)

### Customize Per Diem

In the web interface:
1. Go to **Per Diem Tracker** section
2. Set your daily allowance
3. Select date range
4. Click **Analyze Per Diem**

Via environment variables:
```bash
DAILY_FOOD_ALLOWANCE=100.00  # Change to $100/day
```

### How Meals Are Categorized

Meals are automatically categorized by:

1. **Time of transaction**:
   - Breakfast: 5am - 11am
   - Lunch: 11am - 4pm
   - Dinner: 4pm - 10pm

2. **Description keywords**:
   - Breakfast: coffee, starbucks, bagel, breakfast
   - Lunch: lunch, sandwich, noon
   - Dinner: dinner, evening, supper

### Per Diem Reports Show

- ✅ **Daily compliance** (under/over limit)
- 📊 **Meal-by-meal breakdown**
- 💰 **Total saved or overage**
- 📈 **Compliance rate percentage**
- 🎯 **Recommendations for improvement**

## 🔒 Security Notes

### OAuth Security
- Tokens are stored securely in session
- Refresh tokens auto-renew access
- One-click disconnect available
- No passwords stored

### Scope Limitations
- Only reads emails (read-only access)
- Cannot send or delete emails
- Limited to Concur-related searches

### Data Privacy
- Email content stays local
- Only extracts trip information
- No data sent to third parties
- Can work entirely offline after sync

## 🧪 Testing Features

### Demo Mode Test
```python
# Run in demo mode (no credentials needed)
python oauth_enhanced.py
```

### Test Per Diem Analysis
```python
from per_diem_tracker import PerDiemAnalyzer

analyzer = PerDiemAnalyzer()
# Will use test data to show analysis
```

## 📝 API Endpoints

### Gmail Endpoints
- `GET /auth/google/authorize` - Initiate Gmail OAuth
- `GET /auth/google/callback` - OAuth callback
- `GET /api/gmail/trips` - Fetch Concur trip emails

### Per Diem Endpoints  
- `POST /api/per-diem/analyze` - Analyze expenses vs per diem
- `GET /api/per-diem/config` - Get per diem configuration
- `POST /api/per-diem/config` - Update per diem settings

## 🎯 Use Cases

### 1. Pre-Trip Planning
- See upcoming trips from Concur emails
- Set per diem budgets
- Plan meal expenses

### 2. During Travel
- Track daily meal spending
- Get alerts when approaching limits
- See remaining daily allowance

### 3. Post-Trip Reconciliation
- Compare actual vs per diem
- Generate compliance reports
- Identify savings or overages
- Submit accurate expense reports

## 🚨 Troubleshooting

### "Gmail not connecting"
1. Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env
2. Verify redirect URI matches exactly
3. Check API is enabled in Google Cloud Console

### "No Concur emails found"
1. Verify emails are from @concursolutions.com or @concur.com
2. Check date range of search
3. Try searching manually in Gmail first

### "Per diem not calculating"
1. Ensure expenses are categorized as MEALS
2. Check date format (YYYY-MM-DD)
3. Verify time format (HH:MM)

## 🎉 Success Metrics

After setup, you should see:
- ✅ Gmail connected status
- 📧 List of Concur trip emails
- 💰 Per diem analysis for each day
- 📊 Compliance rate percentage
- 🎯 Clear under/over indicators

## 📚 Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Gmail API Reference](https://developers.google.com/gmail/api/reference/rest)
- [GSA Per Diem Rates](https://www.gsa.gov/travel/plan-book/per-diem-rates)