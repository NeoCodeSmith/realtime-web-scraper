# Terraform Configuration for Real-Time Scraper
# Enforces P2: Cost Cap ($100/mo)

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# P2 Cost Table (Monthly Estimates)
locals {
  cost_table = {
    lambda      = 20  # $20/mo
    api_gateway = 10  # $10/mo
    redis       = 5   # $5/mo
    rds         = 30  # $30/mo
    grafana     = 10  # $10/mo
    buffer      = 25  # $25/mo
    total       = 100 # $100/mo (P2 Cap)
  }
}

# Lambda for Scraper Service
resource "aws_lambda_function" "scraper" {
  function_name = "realtime-scraper"
  runtime       = "python3.9"
  handler       = "scraper.lambda_handler"
  memory_size   = 128
  timeout       = 10  # TBT < 100ms enforced
  
  # Cost Alert: Monitor invocations
  tags = {
    CostCenter = "Scraper"
    P2Cap      = "${local.cost_table.lambda}"
  }
}

# API Gateway
resource "aws_api_gateway_rest_api" "scraper_api" {
  name = "scraper-gateway"
  
  tags = {
    CostCenter = "API"
    P2Cap      = "${local.cost_table.api_gateway}"
  }
}

# Redis (ElastiCache)
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "scraper-redis"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis6.x"
  
  tags = {
    CostCenter = "Queue"
    P2Cap      = "${local.cost_table.redis}"
  }
}

# RDS PostgreSQL
resource "aws_db_instance" "scraper_db" {
  allocated_storage    = 20
  engine               = "postgres"
  instance_class       = "db.t3.micro"
  username             = "scraper"
  password             = "securepassword"
  publicly_accessible  = false
  skip_final_snapshot  = true
  
  tags = {
    CostCenter = "Database"
    P2Cap      = "${local.cost_table.rds}"
  }
}

output "cost_breakdown" {
  value = local.cost_table
}