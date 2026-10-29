#!/bin/bash

# Purchase Redundancy Detection - Setup Script (Linux / macOS / Git Bash on Windows)
# Usage: bash setup.sh            -> full install (with real CLIP model, ~1 GB download)
#        bash setup.sh --no-clip  -> lightweight install (simulated embeddings)

set -e
cd "$(dirname "$0")"

INSTALL_CLIP=1
[[ "$1" == "--no-clip" ]] && INSTALL_CLIP=0

echo "🚀 Setting up Purchase Redundancy Detection System..."
echo ""

# Check Python (python3 on Linux/macOS, python on Windows)
echo "📦 Checking Python installation..."
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &> /dev/null && "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" &> /dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "❌ Python 3.10+ not found. Please install it from https://python.org"
    exit 1
fi
echo "✅ Found $($PYTHON --version)"
echo ""

# Setup Backend
echo "📦 Setting up backend..."
cd backend

if [[ ! -d venv ]]; then
    echo "   Creating virtual environment..."
    $PYTHON -m venv venv
fi

if [[ -f venv/Scripts/python.exe ]]; then
    VENV_PY=venv/Scripts/python
else
    VENV_PY=venv/bin/python
fi

echo "   Installing Python packages..."
$VENV_PY -m pip install --upgrade pip -q
$VENV_PY -m pip install -r requirements-dev.txt -q
if [[ $INSTALL_CLIP == 1 ]]; then
    echo "   Installing CLIP (torch + transformers, this can take a few minutes)..."
    $VENV_PY -m pip install -r requirements-ml.txt -q
fi

cd ..
echo "✅ Backend setup complete"
echo ""

# Setup Frontend
echo "📦 Setting up frontend..."
if ! command -v npm &> /dev/null; then
    echo "⚠️  Node.js/npm not found. Skipping frontend setup."
    echo "   Install Node.js 18+ from: https://nodejs.org"
else
    (cd frontend && npm install)
    echo "✅ Frontend setup complete"
fi
echo ""

# Product catalog (only if missing - keeps product IDs stable)
echo "📦 Checking product catalog..."
if [[ ! -f database/products_700.json ]]; then
    $PYTHON database/generate_700_products.py
fi
(cd backend && $VENV_PY models.py)
echo "✅ Database ready"
echo ""

# .env - never overwrite an existing one (it holds your API key)
if [[ -f .env ]]; then
    echo "📝 .env already exists - left unchanged"
else
    cp .env.example .env
    echo "📝 Created .env from .env.example - add your CLAUDE_API_KEY"
fi
echo ""

if [[ $INSTALL_CLIP == 1 ]]; then
    echo "📥 Downloading the CLIP model (first run only, ~600 MB)..."
    (cd backend && $VENV_PY -c "from clip_integration import CLIPEmbedding; c = CLIPEmbedding(); print('   CLIP mode:', c.mode)")
    echo ""
fi

echo "════════════════════════════════════════════════════════════════"
echo "✅ SETUP COMPLETE!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "🚀 Next steps:"
echo ""
echo "1. Put your Claude API key in .env:   CLAUDE_API_KEY=sk-ant-..."
echo ""
echo "2. Start Backend:"
echo "   cd backend && $VENV_PY main.py"
echo ""
echo "3. Start Frontend (new terminal):"
echo "   cd frontend && npm run dev"
echo ""
echo "4. Open:"
echo "   Frontend: http://localhost:3000"
echo "   API:      http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "5. Run the tests:"
echo "   backend/$VENV_PY -m pytest tests"
echo "════════════════════════════════════════════════════════════════"
