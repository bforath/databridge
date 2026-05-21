#!/bin/bash
# Runs inside LocalStack on startup — creates buckets and seeds SSM parameters.
# In production these would be created via Terraform or the AWS console.
set -e

echo "Creating S3 bucket..."
awslocal s3 mb s3://databridge-exports

echo "Seeding SSM parameters..."
awslocal ssm put-parameter --name "/databridge/SECRET_KEY"   --value "dev-secret-key-do-not-use-in-production" --type SecureString --overwrite
awslocal ssm put-parameter --name "/databridge/DATABASE_URL" --value "postgresql://databridge:databridge@db/databridge" --type SecureString --overwrite
awslocal ssm put-parameter --name "/databridge/REDIS_URL"    --value "redis://redis:6379/0" --type SecureString --overwrite

echo "LocalStack bootstrap complete."
