#!/usr/bin/env python3
"""
测试定时器建模的脚本
展示不同类型的定时器如何被转换为mCRL2
"""

from pathlib import Path
import sys

# 添加scripts目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from bpmn2mcrl2 import convert_bpmn_to_mcrl2

def test_timer_conversion():
    """测试定时器转换"""

    # 获取项目根目录
    project_root = Path(__file__).parent.parent.parent

    test_cases = [
        {
            "name": "loan-granting (周期性定时器)",
            "input": project_root / "samples/sample2/camunda/loan-granting.bpmn",
            "output": project_root / "samples/sample2/mcrl2/loan-granting_output.mcrl2"
        },
        {
            "name": "order-handling (周期性定时器 + 条件边界事件)",
            "input": project_root / "samples/sample2/camunda/order-handling.bpmn",
            "output": project_root / "samples/sample2/mcrl2/order-handling_output.mcrl2"
        }
    ]

    print("=" * 80)
    print("定时器建模测试")
    print("=" * 80)
    print()

    for case in test_cases:
        print(f"测试用例: {case['name']}")
        print(f"输入文件: {case['input']}")
        print(f"输出文件: {case['output']}")
        print("-" * 80)

        # 确保输出目录存在
        output_path = Path(case['output'])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 执行转换
        convert_bpmn_to_mcrl2(str(case['input']), str(case['output']))

        # 读取并显示关键部分
        with open(case['output'], 'r', encoding='utf-8') as f:
            content = f.read()

        print("\n生成的mCRL2代码片段:")
        print("-" * 40)

        # 显示proc部分
        if "proc" in content:
            proc_start = content.index("proc")
            proc_end = content.index("init")
            print(content[proc_start:proc_end].strip())

        print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    test_timer_conversion()
