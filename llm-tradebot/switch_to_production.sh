#!/bin/bash

# ============================================================================
# 数据源切换快速配置脚本
# ============================================================================
# 用途: 帮助用户快速切换到 Binance 生产环境
# 使用: chmod +x switch_to_production.sh && ./switch_to_production.sh
# ============================================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_header() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║$1${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ============================================================================
# 步骤1: 检查环境
# ============================================================================
check_environment() {
    print_header "  步骤1: 检查环境                                             "
    
    # 检查配置文件
    if [ ! -f "config.yaml" ]; then
        print_error "config.yaml 不存在"
        echo "请先复制 config.example.yaml:"
        echo "  cp config.example.yaml config.yaml"
        exit 1
    fi
    print_success "config.yaml 存在"
    
    if [ ! -f ".env" ]; then
        print_warning ".env 不存在，将从 .env.example 复制"
        cp .env.example .env
        print_success ".env 文件已创建"
    else
        print_success ".env 存在"
    fi
    
    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 python3"
        exit 1
    fi
    print_success "Python 环境正常"
}

# ============================================================================
# 步骤2: 配置 API 密钥
# ============================================================================
configure_api_keys() {
    print_header "  步骤2: 配置 API 密钥                                         "
    
    echo ""
    print_info "请输入你的 Binance API 密钥"
    echo ""
    echo "获取方式:"
    echo "  1. 登录 https://www.binance.com"
    echo "  2. 账户 → API 管理"
    echo "  3. 创建 API 密钥"
    echo ""
    print_warning "重要: 请确保你信任此脚本，密钥将写入 .env 文件"
    echo ""
    
    # 读取 API Key
    read -p "Binance API Key (留空跳过): " api_key
    
    if [ -z "$api_key" ]; then
        print_warning "跳过 API 密钥配置"
        print_info "请手动编辑 .env 文件配置密钥"
        return
    fi
    
    # 读取 API Secret
    read -sp "Binance API Secret: " api_secret
    echo ""
    
    if [ -z "$api_secret" ]; then
        print_error "API Secret 不能为空"
        return
    fi
    
    # 写入 .env
    # 使用 sed 替换或追加
    if grep -q "BINANCE_API_KEY=" .env; then
        # macOS 兼容的 sed
        sed -i '' "s/BINANCE_API_KEY=.*/BINANCE_API_KEY=${api_key}/" .env
        sed -i '' "s/BINANCE_API_SECRET=.*/BINANCE_API_SECRET=${api_secret}/" .env
    else
        echo "BINANCE_API_KEY=${api_key}" >> .env
        echo "BINANCE_API_SECRET=${api_secret}" >> .env
    fi
    
    print_success "API 密钥已配置到 .env 文件"
}

# ============================================================================
# 步骤3: 切换到生产环境
# ============================================================================
switch_to_production() {
    print_header "  步骤3: 切换到生产环境                                        "
    
    echo ""
    print_warning "即将切换到 Binance 生产环境"
    print_warning "这将使用真实的市场数据和账户"
    echo ""
    read -p "确认继续? (y/N): " confirm
    
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        print_info "操作已取消"
        exit 0
    fi
    
    # 备份配置文件
    cp config.yaml config.yaml.backup
    print_success "配置文件已备份到 config.yaml.backup"
    
    # 修改 testnet 配置
    # macOS 兼容的 sed
    sed -i '' 's/testnet: true/testnet: false/' config.yaml
    
    print_success "已切换到生产环境 (testnet: false)"
    
    # 显示当前配置
    echo ""
    print_info "当前配置:"
    grep "testnet:" config.yaml
}

# ============================================================================
# 步骤4: 运行测试
# ============================================================================
run_tests() {
    print_header "  步骤4: 运行连接测试                                          "
    
    echo ""
    print_info "正在测试 API 连接..."
    echo ""
    
    # 运行测试脚本
    if python3 test_binance_connection.py; then
        print_success "连接测试通过！"
        return 0
    else
        print_error "连接测试失败"
        print_info "请检查:"
        echo "  1. API 密钥是否正确"
        echo "  2. API 权限是否足够"
        echo "  3. IP 是否在白名单中"
        echo "  4. 网络连接是否正常"
        return 1
    fi
}

# ============================================================================
# 步骤5: 总结
# ============================================================================
print_summary() {
    print_header "  配置完成                                                     "
    
    echo ""
    print_success "数据源已切换到 Binance 生产环境"
    echo ""
    echo "下一步:"
    echo "  1. 运行数据流程脚本验证数据质量:"
    echo "     python show_data_pipeline.py"
    echo ""
    echo "  2. 查看详细文档:"
    echo "     cat DATA_SOURCE_MIGRATION_GUIDE.md"
    echo ""
    echo "  3. 如需回滚到测试网:"
    echo "     sed -i '' 's/testnet: false/testnet: true/' config.yaml"
    echo ""
    
    print_warning "安全提醒:"
    echo "  • 永远不要分享你的 API 密钥"
    echo "  • 定期检查 API 权限"
    echo "  • 先用小额资金测试"
    echo "  • 设置合理的风控参数"
    echo ""
}

# ============================================================================
# 主函数
# ============================================================================
main() {
    clear
    
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║          数据源切换脚本 - Binance 生产环境                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # 执行步骤
    check_environment
    echo ""
    
    configure_api_keys
    echo ""
    
    switch_to_production
    echo ""
    
    if run_tests; then
        echo ""
        print_summary
        exit 0
    else
        echo ""
        print_error "配置过程中出现错误"
        print_info "配置文件已备份到 config.yaml.backup"
        print_info "如需恢复: mv config.yaml.backup config.yaml"
        exit 1
    fi
}

# 运行主函数
main
