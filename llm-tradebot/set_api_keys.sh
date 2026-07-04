#!/bin/bash
# 设置 Binance API 环境变量并运行验证
# 使用方法：
# 1. 编辑此文件，填入您的 API 密钥
# 2. 运行：source set_api_keys.sh
# 3. 运行：python verify_production_setup.py

echo "=================================================="
echo "  设置 Binance API 环境变量"
echo "=================================================="
echo ""
echo "⚠️  请手动编辑此文件，填入您的 API 密钥："
echo ""
echo "方法1：直接在此文件中设置（推荐用于测试）"
echo "  export BINANCE_API_KEY=\"your_api_key_here\""
echo "  export BINANCE_API_SECRET=\"your_api_secret_here\""
echo ""
echo "方法2：添加到 ~/.zshrc（推荐用于永久配置）"
echo "  1. 打开终端"
echo "  2. 运行：nano ~/.zshrc"
echo "  3. 在文件末尾添加："
echo "     export BINANCE_API_KEY=\"your_api_key_here\""
echo "     export BINANCE_API_SECRET=\"your_api_secret_here\""
echo "     export DEEPSEEK_API_KEY=\"your_deepseek_key_here\""
echo "  4. 保存并运行：source ~/.zshrc"
echo ""
echo "=================================================="
echo ""

# 取消下面两行的注释，并填入您的真实 API 密钥
# export BINANCE_API_KEY="your_binance_api_key_here"
# export BINANCE_API_SECRET="your_binance_api_secret_here"

# 验证是否设置成功
if [ -n "$BINANCE_API_KEY" ]; then
    echo "✅ BINANCE_API_KEY 已设置: ${BINANCE_API_KEY:0:10}...${BINANCE_API_KEY: -10}"
else
    echo "❌ BINANCE_API_KEY 未设置"
    echo "   请取消上面的注释并填入您的 API 密钥"
fi

if [ -n "$BINANCE_API_SECRET" ]; then
    echo "✅ BINANCE_API_SECRET 已设置: ${BINANCE_API_SECRET:0:10}...${BINANCE_API_SECRET: -10}"
else
    echo "❌ BINANCE_API_SECRET 未设置"
    echo "   请取消上面的注释并填入您的 API 密钥"
fi

if [ -n "$DEEPSEEK_API_KEY" ]; then
    echo "✅ DEEPSEEK_API_KEY 已设置: ${DEEPSEEK_API_KEY:0:15}...${DEEPSEEK_API_KEY: -10}"
else
    echo "⚠️  DEEPSEEK_API_KEY 未设置（仅影响 LLM 功能）"
fi

echo ""
echo "设置完成后，运行以下命令验证："
echo "  python verify_production_setup.py"
echo ""
