#!/bin/bash
# nlp2sql Development Installation Script
# This script sets up nlp2sql for local development and testing

set -e  # Exit on any error

echo "🚀 nlp2sql - Development Setup"
echo "==============================="

# Check if UV is installed
if ! command -v uv &> /dev/null; then
    echo "❌ UV is not installed"
    echo "💡 Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source ~/.bashrc 2>/dev/null || source ~/.zshrc 2>/dev/null || true
    echo "✅ UV installed successfully"
else
    echo "✅ UV is already installed"
fi

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "src/nlp2sql" ]; then
    echo "❌ Error: Run this script from the nlp2sql project root directory"
    echo "💡 Make sure you're in the directory containing pyproject.toml"
    exit 1
fi

echo ""
echo "📦 Installing dependencies..."
uv sync

echo ""
echo "🔧 Installing nlp2sql in development mode..."
uv pip install -e .

echo ""
echo "🧪 Testing installation..."
if uv run nlp2sql --help > /dev/null 2>&1; then
    echo "✅ CLI installation successful"
else
    echo "❌ CLI installation failed"
    exit 1
fi

# Test Python imports
echo "🐍 Testing Python imports..."
if uv run python -c "import nlp2sql; print('✅ Python imports working')" 2>/dev/null; then
    echo "✅ Python package imports working"
else
    echo "❌ Python package import failed"
    exit 1
fi

echo ""
echo "🎉 Installation completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Set your API keys:"
echo "   export OPENAI_API_KEY=your-openai-key"
echo "   export ANTHROPIC_API_KEY=your-anthropic-key  # optional"
echo "   export GOOGLE_API_KEY=your-google-key        # optional"
echo ""
echo "2. Test your setup:"
echo "   uv run nlp2sql setup"
echo "   uv run nlp2sql validate"
echo ""
echo "3. Run examples:"
echo "   uv run python examples/getting_started/test_api_setup.py"
echo "   uv run python examples/getting_started/basic_usage.py"
echo ""
echo "4. Use the CLI:"
echo "   uv run nlp2sql --help"
echo "   uv run nlp2sql query --database-url postgresql://... --question 'show all users'"
echo ""
echo "🔗 Or run directly without uv (if PATH is configured):"
echo "   nlp2sql --help"