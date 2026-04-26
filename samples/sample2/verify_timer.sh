#!/bin/bash

# 定时器建模验证脚本

echo "=========================================="
echo "定时器建模验证脚本"
echo "=========================================="
echo ""

cd mcrl2

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 验证函数
verify_model() {
    local model=$1
    local base=$(basename $model .mcrl2)

    echo "验证模型: $model"
    echo "------------------------------------------"

    # 1. 检查文件是否存在
    if [ ! -f "$model" ]; then
        echo -e "${RED}❌ 文件不存在${NC}"
        return 1
    fi

    # 2. 检查是否包含时间特性
    if grep -q "t: Real" "$model"; then
        echo -e "${GREEN}✅ 包含时间参数${NC}"
        HAS_TIME=true
    else
        echo -e "${YELLOW}⚠️  无时间参数（可能不是定时器模型）${NC}"
        HAS_TIME=false
    fi

    if grep -q "tau @ t" "$model"; then
        echo -e "${GREEN}✅ 包含时间约束 (tau @ t)${NC}"
    elif [ "$HAS_TIME" = true ]; then
        echo -e "${YELLOW}⚠️  有时间参数但缺少时间约束${NC}"
    fi

    # 3. 语法检查
    echo ""
    echo "语法检查..."
    if [ "$HAS_TIME" = true ]; then
        if mcrl22lps --timed "$model" "${base}_timed.lps" 2>&1 | tee /tmp/mcrl2_output.txt | grep -i "error"; then
            echo -e "${RED}❌ 语法错误${NC}"
            return 1
        else
            echo -e "${GREEN}✅ 语法正确${NC}"
        fi

        # 检查是否有时间警告
        if grep -q "time.*not preserved" /tmp/mcrl2_output.txt; then
            echo -e "${RED}❌ 错误：应该使用 --timed 选项但未使用${NC}"
        fi
    else
        if mcrl22lps "$model" "${base}.lps" 2>&1 | grep -i "error"; then
            echo -e "${RED}❌ 语法错误${NC}"
            return 1
        else
            echo -e "${GREEN}✅ 语法正确${NC}"
        fi
    fi

    # 4. 生成状态空间
    echo ""
    echo "生成状态空间..."
    local lps_file
    if [ "$HAS_TIME" = true ]; then
        lps_file="${base}_timed.lps"
    else
        lps_file="${base}.lps"
    fi

    if lps2lts "$lps_file" "${base}.lts" 2>&1 | tee /tmp/lts_output.txt; then
        echo -e "${GREEN}✅ 状态空间生成成功${NC}"

        # 统计信息
        if command -v ltsinfo &> /dev/null; then
            echo ""
            echo "状态空间统计:"
            ltsinfo "${base}.lts" | grep -E "(Number of states|Number of transitions|Number of action labels)"
        fi

        # 检查死锁
        if grep -q "deadlock" /tmp/lts_output.txt; then
            echo -e "${YELLOW}⚠️  发现死锁（可能是正常的终止状态）${NC}"
        else
            echo -e "${GREEN}✅ 无死锁${NC}"
        fi
    else
        echo -e "${RED}❌ 状态空间生成失败${NC}"
        return 1
    fi

    echo ""
    echo "验证完成！"
    echo ""
    echo "后续操作："
    echo "  - 可视化: ltsgraph ${base}.lts"
    echo "  - 模拟:   lpsxsim $lps_file"
    echo ""

    return 0
}

# 主程序
echo "检查可用的模型文件..."
echo ""

MODELS=(
    "loan-granting_output.mcrl2"
    "order-handling_output.mcrl2"
)

SUCCESS=0
FAILED=0

for model in "${MODELS[@]}"; do
    if [ -f "$model" ]; then
        verify_model "$model"
        if [ $? -eq 0 ]; then
            ((SUCCESS++))
        else
            ((FAILED++))
        fi
        echo "=========================================="
        echo ""
    fi
done

echo "验证总结:"
echo -e "${GREEN}成功: $SUCCESS${NC}"
echo -e "${RED}失败: $FAILED${NC}"
echo ""

# 提供快速测试命令
echo "快速测试命令："
echo "  # 查看loan-granting的状态空间"
echo "  ltsgraph loan-granting.lts"
echo ""
echo "  # 模拟loan-granting"
echo "  lpsxsim loan-granting_timed.lps"
echo ""
