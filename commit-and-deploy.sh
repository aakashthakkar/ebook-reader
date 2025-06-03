#!/bin/bash

# Commit and Deploy Script for eBook Reader
# This script commits changes and triggers the automated CI/CD pipeline

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 eBook Reader - Commit and Deploy${NC}"
echo "=================================="

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Not in a git repository${NC}"
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${YELLOW}📝 Uncommitted changes detected${NC}"
    
    # Show current status
    echo -e "\n${BLUE}Current git status:${NC}"
    git status --short
    
    # Get commit message
    echo -e "\n${YELLOW}Please enter a commit message:${NC}"
    read -r commit_message
    
    if [ -z "$commit_message" ]; then
        echo -e "${RED}❌ Error: Commit message cannot be empty${NC}"
        exit 1
    fi
    
    # Add all changes
    echo -e "\n${BLUE}📦 Staging all changes...${NC}"
    git add .
    
    # Commit changes
    echo -e "${BLUE}💾 Committing changes...${NC}"
    git commit -m "$commit_message"
    
    echo -e "${GREEN}✅ Changes committed successfully${NC}"
else
    echo -e "${GREEN}✅ Working directory is clean${NC}"
fi

# Check current branch
current_branch=$(git branch --show-current)
echo -e "\n${BLUE}Current branch: ${current_branch}${NC}"

if [ "$current_branch" != "main" ]; then
    echo -e "${YELLOW}⚠️  Warning: You're not on the main branch${NC}"
    echo -e "${YELLOW}The CI/CD pipeline only triggers on pushes to 'main'${NC}"
    echo -e "\nWould you like to:"
    echo "1) Push to current branch ($current_branch)"
    echo "2) Switch to main and merge"
    echo "3) Cancel"
    
    read -r choice
    case $choice in
        1)
            echo -e "${BLUE}🚀 Pushing to $current_branch...${NC}"
            git push origin "$current_branch"
            echo -e "${YELLOW}Note: This will not trigger the Docker build${NC}"
            ;;
        2)
            echo -e "${BLUE}🔄 Switching to main...${NC}"
            git checkout main
            git pull origin main
            echo -e "${BLUE}🔀 Merging $current_branch into main...${NC}"
            git merge "$current_branch"
            echo -e "${BLUE}🚀 Pushing to main...${NC}"
            git push origin main
            echo -e "${GREEN}✅ Pushed to main - CI/CD pipeline will trigger${NC}"
            ;;
        3)
            echo -e "${YELLOW}❌ Cancelled${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Invalid choice${NC}"
            exit 1
            ;;
    esac
else
    # We're on main, just push
    echo -e "\n${BLUE}🚀 Pushing to main branch...${NC}"
    git push origin main
    echo -e "${GREEN}✅ Pushed to main - CI/CD pipeline will trigger${NC}"
fi

echo -e "\n${GREEN}🎉 Deployment initiated!${NC}"
echo -e "\n${BLUE}Next steps:${NC}"
echo "1. 🔍 Monitor the build: https://github.com/aakashthakkar/ebook-reader/actions"
echo "2. 📦 Check Docker Hub: https://hub.docker.com/r/thakkaraakash/ebook-reader"
echo "3. 🎯 Test the image: docker run -p 8000:8000 thakkaraakash/ebook-reader:latest"

echo -e "\n${YELLOW}💡 The build typically takes 5-10 minutes to complete${NC}" 