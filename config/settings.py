# Configuration for Real-Time Scraper
# Enforces P2: Cost Cap ($100/mo)

REALTIME_TIMEOUT = 0.1  # 100ms TBT target
REDIS_URL = "redis://localhost:6379/0"
POSTGRES_URL = "postgresql://user:password@localhost:5432/scraper"

# P2 Cost Monitoring
MAX_LAMBDA_COST = 20  # $20/mo
MAX_API_COST = 10     # $10/mo
MAX_REDIS_COST = 5   # $5/mo
MAX_DB_COST = 30      # $30/mo