#!/bin/bash
################################################################################
# push_data.sh - Push Data Hasil ke GitHub
################################################################################
# Script untuk push file hasil data dari RPi5 ke GitHub
# supaya bisa dianalisa di Windows
#
# Usage:
#   chmod +x push_data.sh
#   ./push_data.sh
################################################################################

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Push Data Hasil ke GitHub${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "analyze_all.py" ]; then
    echo -e "${RED}❌ Error: Must run from thesis directory${NC}"
    exit 1
fi

echo -e "${YELLOW}[1/5] Checking data files...${NC}"

# Check if comparison.csv exists
if [ ! -f "results/hasil_real/comparison.csv" ]; then
    echo -e "${RED}❌ Error: results/hasil_real/comparison.csv not found${NC}"
    exit 1
fi

# Show file info
echo -e "${GREEN}✅ Data files found:${NC}"
ls -lh results/hasil_real/comparison.csv
if [ -f "results/hasil_real/comparison_filtered.csv" ]; then
    ls -lh results/hasil_real/comparison_filtered.csv
fi
if [ -f "results/network/callbox_stats.json" ]; then
    ls -lh results/network/callbox_stats.json
fi
echo ""

echo -e "${YELLOW}[2/5] Checking git status...${NC}"
git status --short
echo ""

echo -e "${YELLOW}[3/5] Adding data files...${NC}"
git add results/hasil_real/comparison.csv
if [ -f "results/hasil_real/comparison_filtered.csv" ]; then
    git add results/hasil_real/comparison_filtered.csv
fi
if [ -f "results/network/callbox_stats.json" ]; then
    git add results/network/callbox_stats.json
fi
echo -e "${GREEN}✅ Files staged${NC}"
echo ""

echo -e "${YELLOW}[4/5] Committing...${NC}"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
git commit -m "Add data hasil real - $TIMESTAMP

- comparison.csv: Raw data from RPi5
- Network stats from N3IWF + Callbox
- Ready for analysis on Windows"

echo -e "${GREEN}✅ Committed${NC}"
echo ""

echo -e "${YELLOW}[5/5] Pushing to GitHub...${NC}"
git push
echo -e "${GREEN}✅ Pushed to GitHub${NC}"
echo ""

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ DATA PUSHED TO GITHUB${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Next steps on Windows:${NC}"
echo -e "  1. git pull"
echo -e "  2. python3 filter_data.py --max-total-steps 10000"
echo -e "  3. cp results/hasil_real/comparison_filtered.csv results/hasil_real/comparison.csv"
echo -e "  4. python3 analyze_all.py"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
