#!/bin/bash
# Data Directory Cleanup Script
# Removes old role-based directories and ensures new agent-based structure

set -e

echo "🧹 Starting data directory cleanup..."

# Navigate to data directory
cd "$(dirname "$0")/data"

# Backup old directories (optional)
echo "📦 Creating backup of old directories..."
mkdir -p ../backups/data_backup_$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="../backups/data_backup_$(date +%Y%m%d_%H%M%S)"

# Move old directories to backup
if [ -d "the_oracle" ]; then
    echo "  Moving the_oracle/ → $BACKUP_DIR/"
    mv the_oracle "$BACKUP_DIR/" 2>/dev/null || true
fi

if [ -d "the_strategist" ]; then
    echo "  Moving the_strategist/ → $BACKUP_DIR/"
    mv the_strategist "$BACKUP_DIR/" 2>/dev/null || true
fi

if [ -d "the_critic" ]; then
    echo "  Moving the_critic/ → $BACKUP_DIR/"
    mv the_critic "$BACKUP_DIR/" 2>/dev/null || true
fi

if [ -d "the_guardian" ]; then
    echo "  Moving the_guardian/ → $BACKUP_DIR/"
    mv the_guardian "$BACKUP_DIR/" 2>/dev/null || true
fi

if [ -d "the_executor" ]; then
    echo "  Moving the_executor/ → $BACKUP_DIR/"
    mv the_executor "$BACKUP_DIR/" 2>/dev/null || true
fi

if [ -d "the_prophet" ]; then
    echo "  Moving the_prophet/ → $BACKUP_DIR/"
    mv the_prophet "$BACKUP_DIR/" 2>/dev/null || true
fi

# Remove execution_engine if it's a duplicate
if [ -d "execution_engine" ]; then
    echo "  Moving execution_engine/ → $BACKUP_DIR/"
    mv execution_engine "$BACKUP_DIR/" 2>/dev/null || true
fi

# Ensure new directory structure exists
echo ""
echo "📁 Creating new agent-based directory structure..."

# Agent directories
mkdir -p agents/trend_agent
mkdir -p agents/setup_agent
mkdir -p agents/trigger_agent
mkdir -p agents/bull_bear
mkdir -p agents/strategy_engine
mkdir -p agents/reflection

# Data directories
mkdir -p market_data

# Analytics directories
mkdir -p analytics/indicators
mkdir -p analytics/predictions
mkdir -p analytics/regime

# Execution directories
mkdir -p execution/orders
mkdir -p execution/trades

# Risk directories
mkdir -p risk/audits

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "📊 New directory structure:"
tree -L 2 -d . 2>/dev/null || find . -type d -maxdepth 2 | sort

echo ""
echo "💾 Old directories backed up to: $BACKUP_DIR"
echo ""
echo "🎯 You can now run the bot with the new structure!"
