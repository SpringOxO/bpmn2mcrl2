# 定时器建模验证指南

## 如何验证生成的mCRL2模型是否正确

### 1. 语法验证

首先确保生成的mCRL2代码语法正确：

```bash
cd samples/sample2/mcrl2

# 检查语法（如果能成功生成LPS，说明语法正确）
mcrl22lps --timed loan-granting_output.mcrl2 loan-granting.lps
```

**预期结果：**
- ✅ 成功生成 `.lps` 文件
- ❌ 如果有语法错误，会显示具体的错误信息

### 2. 时间特性验证

#### 2.1 检查是否使用了 --timed 选项

```bash
# 错误的方式（会丢失时间信息）
mcrl22lps loan-granting_output.mcrl2 loan-granting.lps
# 输出警告: "process contains time, which is now not preserved"

# 正确的方式
mcrl22lps --timed loan-granting_output.mcrl2 loan-granting_timed.lps
# 应该没有时间相关的警告
```

#### 2.2 检查生成的代码结构

**对于周期性定时器，应该看到：**

```mcrl2
proc
  process_name(oid: OrderId, t: Real) =  // ✅ 有时间参数 t: Real
    (tau @ t) .                          // ✅ 有时间约束 @ t
    timer_action(oid) .
    ... 业务逻辑 ... .
    process_name(oid, t + 300);          // ✅ 递归调用，时间递增

init
  process_name(order_id(1), 0);          // ✅ 初始时间为 0
```

**对于持续时间定时器，应该看到：**

```mcrl2
(tau @ 300) . timer_action(oid)          // ✅ 延迟300秒
```

### 3. 行为验证

#### 3.1 使用模拟器验证

```bash
# 启动交互式模拟器
lpsxsim loan-granting_timed.lps
```

**在模拟器中检查：**
1. 查看初始状态的参数值
   - 应该看到 `t = 0`（或其他初始时间值）
2. 执行动作后，检查时间参数是否正确更新
   - 周期性定时器：每次循环 `t` 应该增加固定值（如300）
3. 检查时间约束
   - 动作应该在正确的时间点可用

#### 3.2 生成状态空间

```bash
# 生成状态转换系统
lps2lts loan-granting_timed.lps loan-granting_timed.lts

# 可视化状态空间
ltsgraph loan-granting_timed.lts
```

**在状态图中检查：**
1. 是否有循环结构（周期性定时器应该有）
2. 状态转换是否符合预期
3. 是否有死锁或不可达状态

### 4. 语义验证

#### 4.1 对照BPMN模型检查

**检查清单：**

| BPMN元素 | mCRL2对应 | 验证方法 |
|---------|----------|---------|
| 定时器启动事件 | `(tau @ t) . start_timer(oid)` | 检查是否有时间约束 |
| timeCycle | 递归进程 + 时间递增 | 检查是否有 `process(oid, t + interval)` |
| timeDuration | `(tau @ delay)` | 检查延迟值是否正确 |
| 边界定时器 | 并发选择 + 时间约束 | 检查是否有 `+` 操作符 |

#### 4.2 时间值验证

**ISO 8601 持续时间转换：**

```python
# 运行验证脚本
python3 << 'EOF'
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from bpmn2mcrl2 import parse_duration_to_time

# 测试用例
test_cases = [
    ("PT5M", "300"),      # 5分钟 = 300秒
    ("PT1H", "3600"),     # 1小时 = 3600秒
    ("PT30S", "30"),      # 30秒
    ("P1D", "86400"),     # 1天 = 86400秒
    ("PT1H30M", "5400"),  # 1小时30分钟 = 5400秒
]

print("ISO 8601 持续时间转换验证:")
for duration, expected in test_cases:
    result = parse_duration_to_time(duration)
    status = "✅" if result == expected else "❌"
    print(f"{status} {duration} -> {result} (期望: {expected})")
EOF
```

**Cron表达式转换：**

```python
python3 << 'EOF'
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from bpmn2mcrl2 import parse_cron_to_interval

# 测试用例
test_cases = [
    ("0/5 0/1 * 1/1 * ?", "300"),    # 每5分钟
    ("0 0/1 * * * ?", "3600"),       # 每1小时
]

print("\nCron表达式转换验证:")
for cron, expected in test_cases:
    result = parse_cron_to_interval(cron)
    status = "✅" if result == expected else "❌"
    print(f"{status} '{cron}' -> {result} (期望: {expected})")
EOF
```

### 5. 属性验证

使用mCRL2的模型检查功能验证时间属性。

#### 5.1 创建属性文件

创建 `timer_properties.mcf`：

```mcf
% 属性1: 定时器最终会触发
[true*] <true*> exists t: Real . (t > 0)

% 属性2: 时间单调递增
[true*] forall t1, t2: Real . (t1 < t2) => [true*] (t2 >= t1)

% 属性3: 周期性定时器会重复执行
[true*] <true*> [start_timer(order_id(1))] <true*> start_timer(order_id(1))
```

#### 5.2 验证属性

```bash
# 生成PBES
lps2pbes -f timer_properties.mcf loan-granting_timed.lps loan-granting.pbes

# 求解PBES
pbes2bool loan-granting.pbes
```

### 6. 完整验证流程示例

```bash
#!/bin/bash

echo "=== 定时器建模验证流程 ==="

MODEL="loan-granting_output.mcrl2"
BASE="loan-granting"

echo "1. 语法检查..."
if mcrl22lps --timed $MODEL ${BASE}_timed.lps 2>&1 | grep -i "error"; then
    echo "❌ 语法错误"
    exit 1
else
    echo "✅ 语法正确"
fi

echo "2. 生成状态空间..."
if lps2lts ${BASE}_timed.lps ${BASE}_timed.lts; then
    echo "✅ 状态空间生成成功"

    # 统计状态数量
    STATES=$(ltsinfo ${BASE}_timed.lts | grep "Number of states" | awk '{print $4}')
    TRANSITIONS=$(ltsinfo ${BASE}_timed.lts | grep "Number of transitions" | awk '{print $4}')
    echo "   状态数: $STATES"
    echo "   转换数: $TRANSITIONS"
else
    echo "❌ 状态空间生成失败"
    exit 1
fi

echo "3. 检查死锁..."
if lps2lts ${BASE}_timed.lps ${BASE}_timed.lts 2>&1 | grep -i "deadlock"; then
    echo "⚠️  发现死锁"
else
    echo "✅ 无死锁"
fi

echo "4. 可视化（手动检查）..."
echo "   运行: ltsgraph ${BASE}_timed.lts"

echo "5. 模拟（手动检查）..."
echo "   运行: lpsxsim ${BASE}_timed.lps"

echo "=== 验证完成 ==="
```

### 7. 常见问题检查

#### 问题1: 时间信息丢失

**症状：**
```
process contains time, which is now not preserved
```

**解决：**
使用 `--timed` 选项

#### 问题2: 时间参数缺失

**症状：**
进程定义中没有 `t: Real` 参数

**检查：**
- BPMN中是否有定时器事件？
- `sync_state["has_timer"]` 是否被正确设置？

#### 问题3: 时间值不正确

**症状：**
时间间隔与预期不符

**检查：**
- ISO 8601 解析是否正确？
- Cron表达式解析是否正确？
- 运行上面的验证脚本

#### 问题4: 递归调用缺失

**症状：**
周期性定时器只执行一次

**检查：**
- 进程末尾是否有递归调用？
- 时间参数是否正确递增？

### 8. 对比验证

创建一个简单的测试用例，手动验证：

```mcrl2
% 简单的5分钟周期定时器
sort OrderId = struct order_id(pid: Pos);

act
  tick : OrderId;

proc
  Timer(oid: OrderId, t: Real) =
    (tau @ t) . tick(oid) . Timer(oid, t + 300);

init
  Timer(order_id(1), 0);
```

**验证步骤：**
1. 保存为 `simple_timer.mcrl2`
2. 运行 `mcrl22lps --timed simple_timer.mcrl2 simple_timer.lps`
3. 运行 `lpsxsim simple_timer.lps`
4. 在模拟器中检查：
   - 初始状态 `t = 0`
   - 执行 `tick` 后，下一个状态 `t = 300`
   - 再次执行 `tick` 后，`t = 600`
   - 依此类推

### 9. 文档对照

对照生成的代码与文档说明：

- [TIMER_MODELING.md](TIMER_MODELING.md) - 查看建模规范
- [TIMER_IMPROVEMENT.md](TIMER_IMPROVEMENT.md) - 查看改进说明

### 10. 总结检查清单

- [ ] 语法检查通过（能生成LPS）
- [ ] 使用了 `--timed` 选项
- [ ] 周期性定时器有时间参数 `t: Real`
- [ ] 有时间约束 `(tau @ t)`
- [ ] 有递归调用且时间递增
- [ ] 时间值转换正确（ISO 8601 / Cron）
- [ ] 状态空间生成成功
- [ ] 无意外的死锁
- [ ] 模拟器中行为符合预期
- [ ] 与BPMN模型语义一致

## 推荐的验证顺序

1. **快速检查**：语法验证（1分钟）
2. **结构检查**：代码结构对照（2分钟）
3. **行为检查**：模拟器验证（5分钟）
4. **深度检查**：状态空间分析（10分钟）
5. **属性检查**：模型检查（可选，15分钟）

如果前3步都通过，基本可以确认模型是正确的。
