#!/bin/bash
echo "Initializing LocalStack Redshift for nlp2sql testing..."

# Wait for LocalStack to be ready
echo "Waiting for LocalStack to be ready..."
while ! curl -f http://localhost:4566/_localstack/health > /dev/null 2>&1; do
    echo "Waiting for LocalStack..."
    sleep 2
done

echo "LocalStack is ready, setting up Redshift cluster..."

# Set AWS credentials for LocalStack (dummy values work)
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

# Create a Redshift cluster
echo "Creating Redshift cluster..."
aws --endpoint-url=http://localhost:4566 redshift create-cluster \
    --cluster-identifier nlp2sql-test-cluster \
    --node-type dc2.large \
    --master-username testuser \
    --master-user-password testpass123 \
    --db-name testdb \
    --cluster-type single-node \
    --publicly-accessible \
    --region us-east-1 2>&1 || echo "[WARN]  Cluster creation may have failed or cluster already exists"

echo "Waiting for Redshift cluster to be available..."
aws --endpoint-url=http://localhost:4566 redshift wait cluster-available \
    --cluster-identifier nlp2sql-test-cluster \
    --region us-east-1 2>&1 || echo "[WARN]  Cluster wait may have failed or cluster already available"

echo ""
echo "[OK] Redshift cluster setup attempted!"
echo ""
echo "[WARN]  Note: Schema and table creation should be done from outside the container"
echo "   using Python/asyncpg or psql from the host machine, as LocalStack container"
echo "   doesn't have psql installed. See docker/test-redshift.sh for example."
echo ""
# Get port from environment or use default
REDSHIFT_PORT=${REDSHIFT_PORT:-5439}
echo "Connection URLs:"
echo "  - redshift://testuser:testpass123@localhost:${REDSHIFT_PORT}/testdb"
echo "  - postgresql://testuser:testpass123@localhost:${REDSHIFT_PORT}/testdb"
echo ""
echo "LocalStack Redshift initialization script complete!"
