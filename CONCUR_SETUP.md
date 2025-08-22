# SAP Concur API Setup Guide

This guide walks through setting up SAP Concur API integration for automated expense reporting.

## Prerequisites

1. **SAP Concur Account**: You need access to a SAP Concur instance
2. **Developer Access**: Your company must enable API access
3. **Python Environment**: Python 3.7+ with required packages

## Step 1: Register for Concur Developer Access

### For Individual Developers
1. Go to [SAP Concur Developer Center](https://developer.concur.com/)
2. Sign up for a developer account
3. Create a new application in the developer portal

### For Enterprise Users
1. Contact your SAP Concur administrator
2. Request API access for your application
3. Obtain necessary approval from your company's IT/Finance team

## Step 2: Obtain API Credentials

### Required Credentials
You'll need these four pieces of information:

1. **Client ID**: Identifies your application
2. **Client Secret**: Authenticates your application  
3. **Refresh Token**: Allows ongoing access without user login
4. **Base URL**: Your Concur instance URL (usually `https://us.api.concursolutions.com`)

### Getting Credentials

#### Option A: Developer Sandbox
1. In the developer portal, create a test application
2. Note your Client ID and Secret
3. Use sandbox credentials for testing

#### Option B: Production Access
1. Work with your Concur administrator
2. Complete company certification process
3. Obtain production credentials

### Getting a Refresh Token

The refresh token requires user consent and is typically obtained through OAuth flow:

1. **Authorization URL**:
   ```
   https://www.concursolutions.com/net2/oauth2/Login.aspx?client_id=YOUR_CLIENT_ID&scope=user&redirect_uri=YOUR_REDIRECT_URI&response_type=code
   ```

2. **User authorizes** your application
3. **Exchange authorization code** for refresh token using the token endpoint
4. **Store refresh token securely** for ongoing API access

## Step 3: Configure Environment

1. **Copy environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Edit .env file** with your credentials:
   ```bash
   # SAP Concur API Configuration
   CONCUR_BASE_URL=https://us.api.concursolutions.com
   CONCUR_CLIENT_ID=your_client_id_here
   CONCUR_CLIENT_SECRET=your_client_secret_here
   CONCUR_REFRESH_TOKEN=your_refresh_token_here
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Step 4: Test Connection

Test your API connection:

```bash
python concur_api_client.py --test-auth
```

Expected output:
```
Testing Concur authentication...
✓ Authentication successful
✓ Connected as: John Doe
```

## Step 5: Usage Examples

### Basic Expense Report Creation
```bash
# Analyze expenses and create Concur reports
python chase_travel_expense_analyzer.py --plaid --access-token YOUR_TOKEN --create-concur-reports

# Also submit for approval
python chase_travel_expense_analyzer.py --plaid --access-token YOUR_TOKEN --create-concur-reports --submit-to-concur
```

### With Hotel Folio Retrieval
```bash
python chase_travel_expense_analyzer.py \
  --plaid --access-token YOUR_TOKEN \
  --retrieve-folios \
  --create-concur-reports \
  --email-config email_config.json \
  --hotel-credentials hotel_credentials.json
```

## Concur API Capabilities

### What the Integration Does:

1. **Expense Reports**: Creates properly formatted expense reports
2. **Expense Entries**: Adds individual expenses with correct categorization
3. **Receipt Upload**: Attaches receipt images and hotel folios
4. **Automatic Submission**: Submits reports for approval workflow

### Supported Expense Types:
- **LODGING**: Hotel charges
- **AIRFARE**: Flight tickets  
- **MEALS**: Restaurant and food expenses
- **GROUND**: Transportation (Uber, taxi, rental cars)
- **MISCELLANEOUS**: Other business expenses

### Data Mapping:
- Transaction descriptions → Vendor names
- Bank transaction dates → Expense dates
- Location data → Expense locations
- Categories → Concur expense types

## Troubleshooting

### Authentication Issues
```
Error: Authentication failed
```
**Solutions**:
- Verify Client ID and Secret are correct
- Check that refresh token is valid and not expired
- Ensure base URL matches your Concur instance
- Confirm API access is enabled for your account

### Missing Permissions
```
Error: 403 Forbidden
```
**Solutions**:
- Contact Concur administrator to enable required permissions
- Verify user has expense management rights
- Check if company policies restrict API access

### Token Expiration
```
Error: 401 Unauthorized
```
**Solutions**:
- Refresh tokens typically don't expire, but check with admin
- Re-authorize application if refresh token is invalid
- Verify client credentials haven't changed

### Rate Limiting
```
Error: 429 Too Many Requests
```
**Solutions**:
- Implement retry logic with exponential backoff
- Reduce frequency of API calls
- Contact Concur support for rate limit increases

## Security Best Practices

1. **Store credentials securely**: Never commit .env files to version control
2. **Use HTTPS**: All API calls use secure connections
3. **Rotate tokens**: Regularly refresh API credentials
4. **Limit scope**: Only request necessary API permissions
5. **Monitor usage**: Track API calls and unusual activity

## Company-Specific Setup

### Policy Integration
- Configure expense policies in Concur
- Map transaction categories to company expense types
- Set up approval workflows

### Custom Fields
- Add company-specific expense fields
- Map additional transaction data to custom fields
- Configure required vs optional fields

### Reporting Integration
- Set up automated expense submission
- Configure approval notifications
- Integrate with accounting systems

## Support Resources

- [SAP Concur Developer Documentation](https://developer.concur.com/)
- [API Reference](https://developer.concur.com/api-reference/)
- [Community Forums](https://community.concur.com/)
- Your company's Concur administrator

## API Limits and Considerations

- **Rate Limits**: Typically 1000 requests per hour per user
- **Data Retention**: Expense data retained according to company policy  
- **Audit Trail**: All API actions are logged for compliance
- **Currency Support**: Multiple currencies supported with proper configuration