#!/bin/bash
# nlp2sql Development Installation Script
# This script sets up nlp2sql for local development and testing

set -e  # Exit on any error

echo "=========================================="
echo "nlp2sql - Development Setup"
echo "=========================================="
echo ""

# Check if UV is installed
if ! command -v uv &> /dev/null; then
    echo "[ERROR] UV is not installed"
    echo "[INFO] Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source ~/.bashrc 2>/dev/null || source ~/.zshrc 2>/dev/null || true
    echo "[OK] UV installed successfully"
else
    echo "[OK] UV is already installed"
fi

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "src/nlp2sql" ]; then
    echo "[ERROR] Run this script from the nlp2sql project root directory"
    echo "[INFO] Make sure you're in the directory containing pyproject.toml"
    exit 1
fi

echo ""
echo "Installing dependencies..."
uv sync

echo ""
echo "Installing nlp2sql in development mode..."
uv pip install -e .

echo ""
echo "Testing installation..."
if uv run nlp2sql --help > /dev/null 2>&1; then
    echo "[OK] CLI installation successful"
else
    echo "[ERROR] CLI installation failed"
    exit 1
fi

# Test Python imports
echo "Testing Python imports..."
if uv run python -c "import nlp2sql; print('[OK] Python imports working')" 2>/dev/null; then
    echo "[OK] Python package imports working"
else
    echo "[ERROR] Python package import failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "Installation completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Set your API keys:"
echo "   export OPENAI_API_KEY=your-openai-key"
echo "   export ANTHROPIC_API_KEY=your-anthropic-key  # optional"
echo "   export GOOGLE_API_KEY=your-google-key        # optional"
echo ""
echo "2. Optional: Install local embeddings support"
echo "   uv pip install -e \".[embeddings-local]\""
echo "   This reduces package size but requires sentence-transformers"
echo ""
echo "3. Test your setup:"
echo "   uv run nlp2sql setup"
echo "   uv run nlp2sql validate"
echo ""
echo "4. Run examples:"
echo "   uv run python examples/getting_started/test_api_setup.py"
echo "   uv run python examples/getting_started/basic_usage.py"
echo ""
echo "5. Use the CLI:"
echo "   uv run nlp2sql --help"
echo "   uv run nlp2sql query --database-url postgresql://... --question 'show all users'"
echo ""
echo "Or run directly without uv (if PATH is configured):"
echo "   nlp2sql --help"
echo ""