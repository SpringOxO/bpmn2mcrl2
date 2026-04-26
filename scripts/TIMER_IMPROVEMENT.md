# 定时器建模改进总结

## 改进前后对比

### 改进前
定时器事件被建模为普通动作，丢失了时间信息：

```mcrl2
proc
  loan_process(oid: OrderId) =
    start_timereventdefinition(oid) .
    check_credit_score(oid) .
    ...;
```

**问题:** 无法表达定时器的时间约束，无法进行时间相关的验证。

### 改进后
定时器事件使用mCRL2的时间特性建模：

```mcrl2
proc
  loan_process(oid: OrderId, t: Real) =
    (tau @ t) . start_timer(oid) .
    check_credit_score(oid) .
    ... .
    loan_process(oid, t + 300);

init
  loan_process(order_id(1), 0);
```

**优势:**
- ✅ 保留了时间信息
- ✅ 支持周期性定时器
- ✅ 支持持续时间定时器
- ✅ 可以进行时间相关的验证和分析

## 主要特性

### 1. 周期性定时器 (Cycle Timer)
- 解析cron表达式
- 建模为递归过程，时间参数递增
- 示例：每5分钟触发一次

### 2. 持续时间定时器 (Duration Timer)
- 解析ISO 8601持续时间格式
- 使用 `(tau @ delay)` 表示延迟
- 示例：PT5M = 300秒延迟

### 3. 边界定时器事件
- 支持附加到活动的定时器
- 可以与正常流程并发执行

## 技术实现

### 新增函数
1. `extract_timer_info(elem)` - 提取定时器信息
2. `parse_duration_to_time(duration_str)` - 解析ISO 8601持续时间
3. `parse_cron_to_interval(cron_str)` - 解析cron表达式

### 修改的函数
1. `collect_scope()` - 收集定时器信息
2. `make_event_action()` - 识别定时器事件
3. `build_start_scope()` - 添加时间约束
4. `build_boundary_expr()` - 处理边界定时器
5. 主转换逻辑 - 为周期性定时器生成递归过程

## 测试

运行测试脚本：
```bash
cd samples/sample2
python test_timer.py
```

## 文档

详细文档请参考：[TIMER_MODELING.md](TIMER_MODELING.md)

## 示例输出

### loan-granting.bpmn
```mcrl2
% Auto-generated mCRL2 with Collaboration & Parallel Support & Timed Events
sort OrderId = struct order_id(pid: Pos);

act
  check_credit_score, endevent_0q9wl5o, endevent_0zj88y0,
  endevent_1alwvtl, grant_loan, reject_loan_request,
  start_timer : OrderId;

proc
  loan_process(oid: OrderId, t: Real) =
    (tau @ t) . start_timer(oid) .
    check_credit_score(oid) .
    (tau . grant_loan(oid) . endevent_1alwvtl(oid) +
     tau . reject_loan_request(oid) . endevent_0zj88y0(oid)) .
    endevent_0q9wl5o(oid) .
    loan_process(oid, t + 300);

init
  loan_process(order_id(1), 0);
```

## 验证

使用mCRL2工具链验证时间属性：

```bash
# 生成LPS
mcrl22lps --timed loan-granting_output.mcrl2 loan-granting_timed.lps

# 可视化状态空间
lps2lts loan-granting_timed.lps loan-granting_timed.lts
ltsgraph loan-granting_timed.lts

# 模拟执行
lpsxsim loan-granting_timed.lps
```


