#!/bin/bash
# Deploy workflows to n8n server
# Run this on the server after uploading updated JSON files

set -e

N8N_URL="http://localhost:5678"
N8N_API_KEY=""  # Set this before running

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== n8n Workflow Deploy Script ===${NC}"

# Check API key
if [ -z "$N8N_API_KEY" ]; then
    echo -e "${RED}ERROR: N8N_API_KEY not set${NC}"
    echo "Get API key from n8n UI: Settings -> n8n API -> Create API Key"
    echo "Then: export N8N_API_KEY='your-key-here'"
    exit 1
fi

# Function to deploy workflow
deploy_workflow() {
    local file=$1
    local name=$(basename "$file" .json)
    
    echo -e "${YELLOW}Processing: $name${NC}"
    
    # Get existing workflow ID by name
    existing=$(curl -s -X GET "$N8N_URL/api/v1/workflows" \
        -H "X-N8N-API-KEY: $N8N_API_KEY" \
        -H "Content-Type: application/json" | \
        jq -r ".data[] | select(.name | contains(\"$name\")) | .id" | head -1)
    
    # Clean JSON for API
    clean_json=$(cat "$file" | jq '{name, nodes, connections, settings}')
    
    if [ -n "$existing" ]; then
        echo -e "  Found existing workflow ID: $existing"
        echo -e "  Updating..."
        
        response=$(curl -s -X PUT "$N8N_URL/api/v1/workflows/$existing" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$clean_json")
        
        if echo "$response" | jq -e '.data.id' > /dev/null 2>&1; then
            echo -e "${GREEN}  ✓ Updated successfully${NC}"
        else
            echo -e "${RED}  ✗ Update failed${NC}"
            echo "$response" | jq '.'
        fi
    else
        echo -e "  Creating new workflow..."
        
        response=$(curl -s -X POST "$N8N_URL/api/v1/workflows" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$clean_json")
        
        if echo "$response" | jq -e '.data.id' > /dev/null 2>&1; then
            echo -e "${GREEN}  ✓ Created successfully${NC}"
        else
            echo -e "${RED}  ✗ Creation failed${NC}"
            echo "$response" | jq '.'
        fi
    fi
}

# Deploy workflows
cd /root/mvp-auto-summary/n8n-workflows

for workflow in *.json; do
    deploy_workflow "$workflow"
    echo ""
done

echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Open n8n UI: http://84.252.100.93:5678"
echo "2. Verify workflows are updated"
echo "3. Activate workflows if not active"
echo "4. Test manually with 'Execute workflow' button"
