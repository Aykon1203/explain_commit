#!/usr/bin/env bash
#
# install.sh - Installer for git-explain / explain-commit
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="$SCRIPT_DIR/explain_commit.py"
TARGET_DIR="${HOME}/.local/bin"

echo "📦 Installing git-explain / explain-commit..."

# Ensure source file exists and is executable
if [ ! -f "$SOURCE_FILE" ]; then
    echo "❌ Error: explain_commit.py not found in $SCRIPT_DIR"
    exit 1
fi
chmod +x "$SOURCE_FILE"

# Ensure target directory exists
mkdir -p "$TARGET_DIR"

# Create symlinks
ln -sf "$SOURCE_FILE" "$TARGET_DIR/git-explain"
ln -sf "$SOURCE_FILE" "$TARGET_DIR/explain-commit"

echo "✅ Created symlinks in $TARGET_DIR:"
echo "   - git-explain -> $SOURCE_FILE"
echo "   - explain-commit -> $SOURCE_FILE"

# Verify PATH
if [[ ":$PATH:" != *":$TARGET_DIR:"* ]]; then
    echo ""
    echo "⚠️  Notice: $TARGET_DIR is not currently in your \$PATH."
    echo "   Add the following line to your ~/.zshrc or ~/.bashrc:"
    echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
else
    echo "✅ $TARGET_DIR is already in your \$PATH!"
fi

echo ""
echo "🎉 Installation complete!"
echo ""
echo "You can now run any of the following commands from ANY git repository:"
echo "   git explain                 # Smart auto-detect (uncommitted -> unpushed -> latest)"
echo "   git explain --push          # Explain commit(s) about to be pushed"
echo "   git explain --latest        # Explain the latest commit (HEAD)"
echo "   git explain --uncommitted   # Explain uncommitted changes (staged + unstaged)"
echo "   git explain -i              # Interactive menu to select what to explain"
echo "   git explain --copy          # Copy explanation to clipboard"
echo "   explain-commit              # Standalone command"
echo ""
