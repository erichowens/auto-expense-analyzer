# Travel Expense Analyzer - Deployment Guide

This guide covers deploying the Travel Expense Analyzer in various environments.

## 🚀 Quick Start

### Development Mode
```bash
# Clone and setup
git clone <repository-url>
cd travel-expense-analyzer

# Install dependencies
pip install -r requirements.txt

# Create configuration
cp .env.example .env
# Edit .env with your API credentials

# Run the application
python run_web_app.py
```

Access the application at: http://localhost:5000

### Production Mode
```bash
# Set production environment
export FLASK_ENV=production

# Run with Gunicorn
python run_web_app.py
```

## 🐳 Docker Deployment

### Single Container
```bash
# Build the image
docker build -t expense-analyzer .

# Run the container
docker run -p 5000:5000 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/uploads:/app/uploads \
  expense-analyzer
```

### Docker Compose (Recommended)
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## ☁️ Cloud Deployment

### AWS EC2
1. Launch an EC2 instance (Ubuntu 22.04 recommended)
2. Install Docker and Docker Compose
3. Clone the repository
4. Configure environment variables
5. Run with Docker Compose

```bash
# On EC2 instance
sudo apt update
sudo apt install -y docker.io docker-compose
sudo usermod -a -G docker ubuntu

# Clone and configure
git clone <repository-url>
cd travel-expense-analyzer
cp .env.example .env
# Edit .env with credentials

# Start services
docker-compose up -d

# Configure nginx (optional)
sudo apt install nginx
# Copy nginx configuration
```

### Google Cloud Run
1. Build and push to Container Registry
2. Deploy to Cloud Run
3. Set environment variables
4. Configure custom domain (optional)

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT-ID/expense-analyzer

# Deploy
gcloud run deploy expense-analyzer \
  --image gcr.io/PROJECT-ID/expense-analyzer \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Azure Container Instances
```bash
# Create resource group
az group create --name expense-analyzer --location eastus

# Deploy container
az container create \
  --resource-group expense-analyzer \
  --name expense-analyzer \
  --image expense-analyzer:latest \
  --ports 5000 \
  --environment-variables FLASK_ENV=production
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file with the following variables:

```bash
# Required for Plaid integration
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_secret
PLAID_ENV=sandbox  # or development/production

# Required for Concur integration  
CONCUR_CLIENT_ID=your_client_id
CONCUR_CLIENT_SECRET=your_client_secret
CONCUR_REFRESH_TOKEN=your_refresh_token
CONCUR_BASE_URL=https://us.api.concursolutions.com

# Optional: Hotel credentials
MARRIOTT_USERNAME=your_username
MARRIOTT_PASSWORD=your_password
# ... other hotel credentials

# Optional: Email configuration
EMAIL_HOST=imap.gmail.com
EMAIL_PORT=993
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
```

### SSL/TLS Configuration
For production deployments, configure SSL:

1. **Using nginx (recommended):**
   - Obtain SSL certificates (Let's Encrypt, commercial CA)
   - Place certificates in `nginx/ssl/`
   - Update `nginx/nginx.conf`

2. **Using cloud provider SSL:**
   - Configure SSL termination at load balancer
   - Update application to handle forwarded headers

### Database Configuration
The application uses SQLite by default. For production:

1. **SQLite (default):**
   - Suitable for single-instance deployments
   - Data persisted in `data/expenses.db`

2. **PostgreSQL (recommended for production):**
   ```bash
   # Install PostgreSQL adapter
   pip install psycopg2-binary
   
   # Set environment variable
   DATABASE_URL=postgresql://user:pass@host:port/dbname
   ```

## 📊 Monitoring and Logging

### Health Checks
The application provides a health check endpoint:
```
GET /api/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "version": "1.0.0",
  "components": {
    "database": "healthy",
    "plaid": "available",
    "modules": "available"
  }
}
```

### Logging
Application logs are written to stdout/stderr. Configure log aggregation:

1. **Docker logs:**
   ```bash
   docker-compose logs -f expense-analyzer
   ```

2. **Cloud logging:**
   - AWS CloudWatch
   - Google Cloud Logging
   - Azure Monitor

### Monitoring
Monitor these metrics:
- Application response time
- Error rates
- Database connection status
- API integration status (Plaid, Concur)
- Memory and CPU usage

## 🔐 Security Considerations

### API Keys and Secrets
- Store sensitive data in environment variables
- Use container secrets management
- Rotate keys regularly
- Monitor API usage

### Network Security
- Use HTTPS for all communication
- Configure firewall rules
- Implement rate limiting
- Use VPC/private networks

### Data Security
- Encrypt database at rest
- Backup data regularly
- Implement data retention policies
- Secure file uploads

## 🚨 Troubleshooting

### Common Issues

1. **Plaid connection fails:**
   - Verify API credentials in .env
   - Check Plaid environment (sandbox/development/production)
   - Ensure network connectivity

2. **Database errors:**
   - Check file permissions on data directory
   - Verify disk space
   - Check database file corruption

3. **Upload failures:**
   - Check uploads directory permissions
   - Verify file size limits
   - Check available disk space

4. **Memory issues:**
   - Increase container memory limits
   - Monitor memory usage
   - Optimize worker count

### Debug Mode
Enable debug mode for troubleshooting:
```bash
export FLASK_ENV=development
python run_web_app.py
```

### Log Analysis
Check application logs for errors:
```bash
# Docker logs
docker-compose logs expense-analyzer | grep ERROR

# Application logs
tail -f /var/log/expense-analyzer.log
```

## 📝 Maintenance

### Backup
Regular backup procedures:

1. **Database backup:**
   ```bash
   cp data/expenses.db data/expenses.db.backup.$(date +%Y%m%d)
   ```

2. **Configuration backup:**
   ```bash
   tar -czf config-backup.tar.gz .env nginx/ docker-compose.yml
   ```

3. **Automated backups:**
   - Set up cron jobs
   - Use cloud backup services
   - Test restore procedures

### Updates
Update the application:

1. **Development:**
   ```bash
   git pull origin main
   pip install -r requirements.txt
   python run_web_app.py
   ```

2. **Production (Docker):**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

### Scaling
For high-traffic scenarios:

1. **Horizontal scaling:**
   - Use load balancer
   - Deploy multiple instances
   - Configure session storage (Redis)

2. **Database scaling:**
   - Use PostgreSQL with read replicas
   - Implement connection pooling
   - Monitor query performance

## 📞 Support

For deployment assistance:
1. Check the troubleshooting section
2. Review application logs
3. Test health check endpoint
4. Verify configuration files
5. Contact system administrator

---

**Last Updated:** January 2024  
**Version:** 1.0.0