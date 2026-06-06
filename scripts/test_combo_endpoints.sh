#!/bin/bash

###############################################################################
# Combo API Endpoints - Testing Script
#
# Usage: ./test_combo_endpoints.sh [STORE_SLUG] [BASE_URL]
# Default: ./test_combo_endpoints.sh ce-saladas http://localhost:8001
#
# This script tests all combo endpoints with various scenarios
###############################################################################

set -e

# Configuration
STORE_SLUG=${1:-ce-saladas}
BASE_URL=${2:-http://localhost:8001}
API_PATH="${BASE_URL}/api/v1/stores"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function to print test headers
print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"
}

# Helper function to run test
run_test() {
    local test_name=$1
    local expected_status=$2
    local curl_cmd=$3

    ((TESTS_RUN++))

    echo -e "${YELLOW}Test ${TESTS_RUN}: ${test_name}${NC}"
    echo "Command: $curl_cmd"

    # Execute and capture response
    response=$(eval "$curl_cmd" 2>/dev/null)
    status_code=$(echo "$response" | tail -1)

    # Extract actual status code using curl -w
    actual_status=$(eval "$curl_cmd" 2>/dev/null | tail -1 | grep -oE '^[0-9]+$' || echo "000")

    # Better way: use curl -w option
    actual_status=$(curl -s -o /dev/null -w "%{http_code}" $(echo "$curl_cmd" | sed "s/.*curl -X [^ ]* //" | sed 's/ -.*//' | tr -d "'"))

    if [ "$actual_status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Status: $actual_status)"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC} (Expected: $expected_status, Got: $actual_status)"
        ((TESTS_FAILED++))
    fi

    echo ""
}

# Start testing
clear
echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════════╗
║          Combo API Endpoints - Testing Suite                         ║
╚═══════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}\n"

echo "Configuration:"
echo "  Store Slug: $STORE_SLUG"
echo "  Base URL: $BASE_URL"
echo "  API Path: $API_PATH"
echo ""

###############################################################################
# TEST SUITE 1: LIST COMBOS
###############################################################################

print_header "TEST SUITE 1: LIST COMBOS (ComboListView)"

# Test 1.1: List all combos
echo "Executing: GET $API_PATH/$STORE_SLUG/combos/"
RESPONSE=$(curl -s "$API_PATH/$STORE_SLUG/combos/")
COMBO_COUNT=$(echo "$RESPONSE" | jq '.count // 0' 2>/dev/null || echo "0")
COMBO_ID=$(echo "$RESPONSE" | jq -r '.results[0].id // empty' 2>/dev/null)

echo "Found $COMBO_COUNT combos"
if [ -n "$COMBO_ID" ]; then
    echo -e "${GREEN}✓ Sample combo ID: $COMBO_ID${NC}"
fi
echo ""

# Test 1.2: List with is_active filter
echo "Test: GET $API_PATH/$STORE_SLUG/combos/?is_active=true"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/$STORE_SLUG/combos/?is_active=true")
if [ "$STATUS" = "200" ]; then
    echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ FAIL${NC} (Status: $STATUS)"
    ((TESTS_FAILED++))
fi
((TESTS_RUN++))
echo ""

# Test 1.3: Pagination
echo "Test: GET $API_PATH/$STORE_SLUG/combos/?page_size=5"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/$STORE_SLUG/combos/?page_size=5")
RESULTS=$(curl -s "$API_PATH/$STORE_SLUG/combos/?page_size=5" | jq '.results | length')
if [ "$STATUS" = "200" ] && [ "$RESULTS" -le 5 ]; then
    echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS, Results: $RESULTS)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}"
    ((TESTS_FAILED++))
fi
((TESTS_RUN++))
echo ""

# Test 1.4: Invalid store
echo "Test: GET $API_PATH/invalid-store/combos/"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/invalid-store/combos/")
if [ "$STATUS" = "404" ]; then
    echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS - Store not found)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ FAIL${NC} (Expected 404, Got: $STATUS)"
    ((TESTS_FAILED++))
fi
((TESTS_RUN++))
echo ""

###############################################################################
# TEST SUITE 2: GET COMBO DETAILS
###############################################################################

print_header "TEST SUITE 2: GET COMBO DETAILS (ComboDetailView)"

if [ -z "$COMBO_ID" ]; then
    echo -e "${YELLOW}SKIP: No combos found in database${NC}"
    echo "Create combos first using the admin panel"
else
    # Test 2.1: Get valid combo
    echo "Test: GET $API_PATH/$STORE_SLUG/combos/$COMBO_ID/"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/$STORE_SLUG/combos/$COMBO_ID/")
    if [ "$STATUS" = "200" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS)"
        ((TESTS_PASSED++))

        # Display combo details
        COMBO_NAME=$(curl -s "$API_PATH/$STORE_SLUG/combos/$COMBO_ID/" | jq -r '.name')
        COMBO_PRICE=$(curl -s "$API_PATH/$STORE_SLUG/combos/$COMBO_ID/" | jq -r '.price')
        echo "  Combo: $COMBO_NAME (Price: R$ $COMBO_PRICE)"
    else
        echo -e "${RED}✗ FAIL${NC} (Status: $STATUS)"
        ((TESTS_FAILED++))
    fi
    ((TESTS_RUN++))
    echo ""

    # Test 2.2: Invalid UUID format
    echo "Test: GET $API_PATH/$STORE_SLUG/combos/invalid-id/"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/$STORE_SLUG/combos/invalid-id/")
    if [ "$STATUS" = "400" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS - Invalid UUID rejected)"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC} (Expected 400, Got: $STATUS)"
        ((TESTS_FAILED++))
    fi
    ((TESTS_RUN++))
    echo ""

    # Test 2.3: Non-existent combo
    echo "Test: GET $API_PATH/$STORE_SLUG/combos/00000000-0000-0000-0000-000000000000/"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/$STORE_SLUG/combos/00000000-0000-0000-0000-000000000000/")
    if [ "$STATUS" = "404" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS - Combo not found)"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC} (Expected 404, Got: $STATUS)"
        ((TESTS_FAILED++))
    fi
    ((TESTS_RUN++))
    echo ""
fi

###############################################################################
# TEST SUITE 3: ADD COMBO TO CART
###############################################################################

print_header "TEST SUITE 3: ADD COMBO TO CART (AddComboToCartView)"

if [ -z "$COMBO_ID" ]; then
    echo -e "${YELLOW}SKIP: No combos found in database${NC}"
else
    # Test 3.1: Add valid combo to cart
    echo "Test: POST $API_PATH/$STORE_SLUG/cart/add-combo/"

    CART_RESPONSE=$(curl -s -X POST "$API_PATH/$STORE_SLUG/cart/add-combo/" \
      -H "Content-Type: application/json" \
      -d "{
        \"combo_id\": \"$COMBO_ID\",
        \"quantity\": 1,
        \"selections\": {}
      }")

    CART_ID=$(echo "$CART_RESPONSE" | jq -r '.cart_id // empty')

    if [ -n "$CART_ID" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Combo added to cart)"
        echo "  Cart ID: $CART_ID"
        echo "  Item Count: $(echo "$CART_RESPONSE" | jq '.item_count')"
        echo "  Subtotal: $(echo "$CART_RESPONSE" | jq -r '.subtotal')"
        ((TESTS_PASSED++))
    else
        ERROR_MSG=$(echo "$CART_RESPONSE" | jq -r '.detail // .errors // "Unknown error"')
        echo -e "${RED}✗ FAIL${NC} (Error: $ERROR_MSG)"
        ((TESTS_FAILED++))
    fi
    ((TESTS_RUN++))
    echo ""

    # Test 3.2: Missing combo_id
    echo "Test: POST $API_PATH/$STORE_SLUG/cart/add-combo/ (missing combo_id)"

    RESPONSE=$(curl -s -X POST "$API_PATH/$STORE_SLUG/cart/add-combo/" \
      -H "Content-Type: application/json" \
      -d '{"quantity": 1}')

    ERROR=$(echo "$RESPONSE" | jq -r '.detail // empty')

    if [ -n "$ERROR" ] && [[ "$ERROR" == *"combo_id"* ]]; then
        echo -e "${GREEN}✓ PASS${NC} (Validation error caught)"
        echo "  Error: $ERROR"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC} (Expected validation error)"
        ((TESTS_FAILED++))
    fi
    ((TESTS_RUN++))
    echo ""

    # Test 3.3: Invalid quantity
    echo "Test: POST $API_PATH/$STORE_SLUG/cart/add-combo/ (invalid quantity)"

    RESPONSE=$(curl -s -X POST "$API_PATH/$STORE_SLUG/cart/add-combo/" \
      -H "Content-Type: application/json" \
      -d "{
        \"combo_id\": \"$COMBO_ID\",
        \"quantity\": \"invalid\",
        \"selections\": {}
      }")

    ERROR=$(echo "$RESPONSE" | jq -r '.detail // empty')

    if [ -n "$ERROR" ] && [[ "$ERROR" == *"Quantidade"* ]]; then
        echo -e "${GREEN}✓ PASS${NC} (Quantity validation enforced)"
        echo "  Error: $ERROR"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC} (Expected quantity error)"
        ((TESTS_FAILED++))
    fi
    ((TESTS_RUN++))
    echo ""
fi

###############################################################################
# TEST SUITE 4: URL PATTERNS
###############################################################################

print_header "TEST SUITE 4: URL PATTERN VERIFICATION"

# Test 4.1: Canonical pattern
echo "Test: Canonical URL /api/v1/stores/$STORE_SLUG/combos/"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/$STORE_SLUG/combos/")
if [ "$STATUS" = "200" ]; then
    echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ FAIL${NC} (Status: $STATUS)"
    ((TESTS_FAILED++))
fi
((TESTS_RUN++))
echo ""

# Test 4.2: Legacy pattern
echo "Test: Legacy URL /api/v1/stores/s/$STORE_SLUG/combos/"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_PATH/s/$STORE_SLUG/combos/")
if [ "$STATUS" = "200" ]; then
    echo -e "${GREEN}✓ PASS${NC} (Status: $STATUS - Backward compatible)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ FAIL${NC} (Status: $STATUS)"
    ((TESTS_FAILED++))
fi
((TESTS_RUN++))
echo ""

# Test 4.3: Content-Type
echo "Test: JSON Content-Type header"
CONTENT_TYPE=$(curl -s -I "$API_PATH/$STORE_SLUG/combos/" | grep -i content-type | cut -d' ' -f2- | tr -d '\r')
if [[ "$CONTENT_TYPE" == *"application/json"* ]]; then
    echo -e "${GREEN}✓ PASS${NC} (Content-Type: $CONTENT_TYPE)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ FAIL${NC} (Content-Type: $CONTENT_TYPE)"
    ((TESTS_FAILED++))
fi
((TESTS_RUN++))
echo ""

###############################################################################
# SUMMARY
###############################################################################

print_header "TEST SUMMARY"

echo "Total Tests Run: $TESTS_RUN"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}   ALL TESTS PASSED! ✓${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}\n"
    exit 0
else
    echo -e "\n${RED}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}   SOME TESTS FAILED!${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════${NC}\n"
    exit 1
fi
