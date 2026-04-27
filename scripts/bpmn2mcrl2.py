import xml.etree.ElementTree as ET
import re
import argparse
from pathlib import Path
from collections import deque

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

TASK_NODE_TYPES = {
    "serviceTask",
    "receiveTask",
    "sendTask",
    "userTask",
    "task",
    "scriptTask",
}

FLOW_NODE_TYPES = TASK_NODE_TYPES | {
    "startEvent",
    "endEvent",
    "parallelGateway",
    "exclusiveGateway",
    "subProcess",
    "boundaryEvent",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
}

EVENT_DEFINITION_TYPES = {
    "timerEventDefinition",
    "timeEventDefinition",
    "conditionalEventDefinition",
    "messageEventDefinition",
    "signalEventDefinition",
    "errorEventDefinition",
}

def clean_name(name):
    """清理名称以符合 mCRL2 规范"""
    if not name:
        return "unnamed_action"
    clean = re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_").lower()
    return clean if clean else "action"

def camel_to_snake(name):
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return clean_name(name)

def parse_duration_to_time(duration_str):
    """
    解析ISO 8601持续时间格式到mCRL2时间值（秒）
    """
    duration_str = duration_str.strip()
    if duration_str.startswith("PT"):
        time_part = duration_str[2:]
        total_seconds = 0
        if "H" in time_part:
            hours = int(time_part.split("H")[0])
            total_seconds += hours * 3600
            time_part = time_part.split("H")[1]
        if "M" in time_part:
            minutes = int(time_part.split("M")[0])
            total_seconds += minutes * 60
            time_part = time_part.split("M")[1]
        if "S" in time_part:
            seconds = int(time_part.split("S")[0])
            total_seconds += seconds
        return str(total_seconds)
    elif duration_str.startswith("P"):
        date_part = duration_str[1:]
        total_seconds = 0
        if "D" in date_part:
            days = int(date_part.split("D")[0])
            total_seconds += days * 86400
        return str(total_seconds)
    return "0"

def parse_cron_to_interval(cron_str):
    """
    解析简单的cron表达式到时间间隔（秒）
    """
    parts = cron_str.strip().split()
    if len(parts) < 6:
        return None
    minute_field = parts[0]
    hour_field = parts[1]
    if "/" in minute_field:
        minute_parts = minute_field.split("/")
        if len(minute_parts) == 2:
            interval_minutes = int(minute_parts[1])
            return str(interval_minutes * 60)
    if "/" in hour_field:
        hour_parts = hour_field.split("/")
        if len(hour_parts) == 2:
            interval_hours = int(hour_parts[1])
            return str(interval_hours * 3600)
    return None

def parse_condition(expr):
    """将 BPMN 表达式转换为 mCRL2 守卫语法"""
    if not expr:
        return "true"
    # 移除 ${ ... }
    match = re.search(r"\$\{(.*?)\}", expr)
    if match:
        expr = match.group(1)
    # 简单的语法转换
    expr = expr.replace("&&", "&&").replace("||", "||")
    expr = expr.replace("==", "==").replace("!=", "!=")
    return f"({expr.strip()})"

def extract_variables(expr):
    """从表达式中提取变量名"""
    if not expr:
        return set()
    clean_expr = expr
    match = re.search(r"\$\{(.*?)\}", expr)
    if match:
        clean_expr = match.group(1)
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", clean_expr)
    reserved = {"true", "false", "and", "or", "Int", "Real", "Bool", "tau", "delta"}
    return {t for t in tokens if t not in reserved and not t.isdigit()}


def convert_bpmn_to_mcrl2(bpmn_filepath, output_filepath, enable_timer=True):
    print(f"正在解析 BPMN 协作模型: {bpmn_filepath} ...")
    tree = ET.parse(bpmn_filepath)
    root = tree.getroot()
    ns = {"bpmn": BPMN_NS}

    sync_state = {
        "count": 0,
        "rules": [],
        "all_sync_actions": set(),
        "extra_procs": [],
        "init_procs": [],
        "messages": [],
        "exact_msg_nodes": {},
        "used_actions": set(),
        "warnings": [],
        "has_timer": False,
        "has_cycle_timer": False,
        "timer_info": {},
        "all_vars": set(),
    }

    def node_type(elem):
        return elem.tag.split("}", 1)[-1]

    def seq(exprs):
        parts = [e for e in exprs if e and e != "delta" and e != ""]
        return " . ".join(parts) if parts else "delta"

    def choice(exprs):
        parts = [e for e in exprs if e and e != ""]
        if not parts:
            return "delta"
        if len(parts) == 1:
            return parts[0]
        return f"({' + '.join(parts)})"

    def first_successors(node_id, ctx):
        return ctx["flows"].get(node_id, [])

    def event_definition_types(elem):
        return [
            node_type(child)
            for child in list(elem)
            if node_type(child) in EVENT_DEFINITION_TYPES
        ]

    def extract_timer_info(elem):
        timer_def = elem.find("bpmn:timerEventDefinition", ns)
        if timer_def is None:
            return None

        info = {"type": None, "value": None}
        time_cycle = timer_def.find("bpmn:timeCycle", ns)
        if time_cycle is not None and time_cycle.text:
            info["type"] = "cycle"
            info["value"] = time_cycle.text.strip()
            return info

        time_date = timer_def.find("bpmn:timeDate", ns)
        if time_date is not None and time_date.text:
            info["type"] = "date"
            info["value"] = time_date.text.strip()
            return info

        time_duration = timer_def.find("bpmn:timeDuration", ns)
        if time_duration is not None and time_duration.text:
            info["type"] = "duration"
            info["value"] = time_duration.text.strip()
            return info

        return None

    def collect_scope(scope_elem):
        ctx = {
            "nodes": {},
            "types": {},
            "starts": [],
            "flows": {},
            "flow_names": {},
            "subprocesses": {},
            "boundary_events": {},
            "boundary_details": {},
            "event_definitions": {},
            "timer_info": {},
            "flow_conditions": {},
            "variables": set(),
        }

        for elem in list(scope_elem):
            tag = node_type(elem)
            if tag in FLOW_NODE_TYPES and "id" in elem.attrib:
                eid = elem.attrib["id"]
                ctx["nodes"][eid] = elem.attrib.get("name", eid)
                ctx["types"][eid] = tag
                ctx["event_definitions"][eid] = event_definition_types(elem)

                if "timerEventDefinition" in ctx["event_definitions"][eid] and enable_timer:
                    timer_info = extract_timer_info(elem)
                    if timer_info:
                        ctx["timer_info"][eid] = timer_info
                        sync_state["has_timer"] = True
                        sync_state["timer_info"][eid] = timer_info

                if tag == "startEvent":
                    ctx["starts"].append(eid)
                elif tag == "subProcess":
                    inner_ctx = collect_scope(elem)
                    ctx["subprocesses"][eid] = inner_ctx
                    ctx["variables"].update(inner_ctx["variables"])
                    if elem.find("bpmn:multiInstanceLoopCharacteristics", ns) is not None:
                        sync_state["warnings"].append(
                            f"subProcess {eid} contains multiInstanceLoopCharacteristics; "
                            "converted as a single instance."
                        )
                elif tag == "boundaryEvent":
                    attached_to = elem.attrib.get("attachedToRef")
                    if attached_to:
                        ctx["boundary_events"].setdefault(attached_to, []).append(eid)
                    condition_texts = [
                        (condition.text or "").strip()
                        for condition in elem.findall(".//bpmn:condition", ns)
                        if (condition.text or "").strip()
                    ]
                    ctx["boundary_details"][eid] = {
                        "attached_to": attached_to,
                        "cancel_activity": elem.attrib.get("cancelActivity", "true") != "false",
                        "condition_texts": condition_texts,
                        "is_conditional": "conditionalEventDefinition" in ctx["event_definitions"][eid],
                    }

            elif tag == "sequenceFlow":
                src = elem.attrib.get("sourceRef")
                tgt = elem.attrib.get("targetRef")
                if src and tgt:
                    ctx["flows"].setdefault(src, []).append(tgt)
                    ctx["flow_names"][(src, tgt)] = elem.attrib.get("name", "")

                    cond_elem = elem.find("bpmn:conditionExpression", ns)
                    if cond_elem is None:
                        for child in elem:
                            if child.tag.endswith("conditionExpression"):
                                cond_elem = child
                                break
                    if cond_elem is not None and cond_elem.text:
                        cond_text = cond_elem.text.strip()
                        ctx["flow_conditions"][(src, tgt)] = parse_condition(cond_text)
                        ctx["variables"].update(extract_variables(cond_text))

        return ctx

    process_contexts = {}
    for process in root.findall(".//bpmn:process", ns):
        p_id = process.attrib.get("id", "Process")
        ctx = collect_scope(process)
        process_contexts[p_id] = ctx
        sync_state["all_vars"].update(ctx["variables"])

    vars_list = sorted(list(sync_state["all_vars"]))
    params_def = "".join([f", {v}: Int" for v in vars_list])
    params_call = "".join([f", {v}" for v in vars_list])
    params_init = "".join([", 0" for _ in vars_list])

    part_to_proc = {}
    for part in root.findall(".//bpmn:participant", ns):
        part_to_proc[part.attrib.get("id")] = part.attrib.get("processRef")

    node_to_proc = {}
    for process in root.findall(".//bpmn:process", ns):
        p_id = process.attrib.get("id")
        for elem in process.iter():
            tag = node_type(elem)
            if "id" in elem.attrib and tag != "sequenceFlow":
                node_to_proc[elem.attrib["id"]] = p_id

    for mflow in root.findall(".//bpmn:messageFlow", ns):
        src = mflow.attrib.get("sourceRef")
        tgt = mflow.attrib.get("targetRef")
        m_name = clean_name(mflow.attrib.get("name", "msg"))

        src_proc = part_to_proc.get(src) or node_to_proc.get(src)
        tgt_proc = part_to_proc.get(tgt) or node_to_proc.get(tgt)

        sync_state["messages"].append({
            "name": m_name,
            "src_proc": src_proc,
            "tgt_proc": tgt_proc,
        })

        if src in node_to_proc:
            sync_state["exact_msg_nodes"][src] = ("s", m_name)
        if tgt in node_to_proc:
            sync_state["exact_msg_nodes"][tgt] = ("r", m_name)

        sync_state["rules"].append(f"s_{m_name} | r_{m_name} -> c_{m_name}")
        sync_state["all_sync_actions"].update({f"s_{m_name}", f"r_{m_name}", f"c_{m_name}"})

    def get_reachable(start, flows_map):
        q, seen = deque([start]), set()
        while q:
            curr = q.popleft()
            if curr not in seen:
                seen.add(curr)
                q.extend(flows_map.get(curr, []))
        return seen

    def incoming_counts(flows_map):
        counts = {}
        for targets in flows_map.values():
            for target in targets:
                counts[target] = counts.get(target, 0) + 1
        return counts

    def find_join(branch_starts, flows_map):
        reach_sets = [get_reachable(s, flows_map) for s in branch_starts]
        candidates = set.intersection(*reach_sets) if reach_sets else set()
        if not candidates:
            return None

        incoming = incoming_counts(flows_map)
        merge_candidates = [c for c in candidates if incoming.get(c, 0) > 1 and c not in branch_starts]
        if merge_candidates:
            return sorted(merge_candidates)[0]
        return sorted(candidates)[0]

    def make_event_action(node_id, ctx, prefix="event"):
        raw_name = ctx["nodes"].get(node_id, node_id)
        defs = ctx["event_definitions"].get(node_id, [])

        if "timerEventDefinition" in defs and node_id in ctx.get("timer_info", {}):
            timer_info = ctx["timer_info"][node_id]
            base = clean_name(raw_name if raw_name and raw_name != node_id else "timer")
            action_name = f"{prefix}_{base}"
            sync_state["used_actions"].add(action_name)
            return f"{action_name}(oid)"

        base = clean_name(raw_name if raw_name and raw_name != node_id else "_".join(defs) or node_id)
        if base.startswith(prefix + "_"):
            action_name = base
        else:
            action_name = f"{prefix}_{base}"
        sync_state["used_actions"].add(action_name)
        return f"{action_name}(oid)"

    def make_node_action(node_id, ctx, current_proc_id):
        ntype = ctx["types"].get(node_id)

        if ntype == "endEvent":
            name = clean_name(ctx["nodes"].get(node_id, "end_event"))
            sync_state["used_actions"].add(name)
            return f"{name}(oid)"

        if ntype in {"boundaryEvent", "intermediateCatchEvent", "intermediateThrowEvent"}:
            prefix = "boundary" if ntype == "boundaryEvent" else "event"
            action = make_event_action(node_id, ctx, prefix=prefix)

            if node_id in ctx.get("timer_info", {}):
                timer_info = ctx["timer_info"][node_id]
                if timer_info["type"] == "duration":
                    delay = parse_duration_to_time(timer_info["value"])
                    return f"(tau @ {delay}) . {action}"

            return action

        if ntype == "startEvent":
            defs = ctx["event_definitions"].get(node_id, [])
            if defs:
                action = make_event_action(node_id, ctx, prefix="start")
                if "timerEventDefinition" in defs and node_id in ctx.get("timer_info", {}):
                    timer_info = ctx["timer_info"][node_id]
                    if timer_info["type"] == "duration":
                        delay = parse_duration_to_time(timer_info["value"])
                        return f"{action} @ {delay}"
                    elif timer_info["type"] == "cycle":
                        sync_state["warnings"].append(
                            f"Timer cycle '{timer_info['value']}' at {node_id} modeled as separate process trigger"
                        )
                        return action
                    else:
                        return action
                return action
            return ""

        raw_name = ctx["nodes"].get(node_id, "")
        base_action_name = clean_name(raw_name if raw_name else node_id)

        if node_id in sync_state["exact_msg_nodes"]:
            role, m_name = sync_state["exact_msg_nodes"][node_id]
            msg_action = f"{role}_{m_name}"
            sync_state["used_actions"].add(msg_action)
            
            if ntype in TASK_NODE_TYPES:
                sync_state["used_actions"].add(base_action_name)
                if role == "s":
                    return f"{base_action_name}(oid) . {msg_action}(oid)"
                else:
                    return f"{msg_action}(oid) . {base_action_name}(oid)"
            else:
                return f"{msg_action}(oid)"

        sync_state["used_actions"].add(base_action_name)

        return f"{base_action_name}(oid)"

    def build_boundary_expr(boundary_id, ctx, current_proc_id, stop_node=None, visited=None):
        boundary_action = make_node_action(boundary_id, ctx, current_proc_id)

        if boundary_id in ctx.get("timer_info", {}):
            timer_info = ctx["timer_info"][boundary_id]
            if timer_info["type"] == "duration":
                delay = parse_duration_to_time(timer_info["value"])
                boundary_action = f"(tau @ {delay}) . {boundary_action}"

        next_nodes = first_successors(boundary_id, ctx)
        tails = [
            build_expr(n, ctx, current_proc_id, stop_node=stop_node, visited=set(visited or set()))
            for n in next_nodes
        ]
        return seq([boundary_action, choice(tails)])

    def with_boundary_alternatives(node_id, normal_expr, ctx, current_proc_id, stop_node=None, visited=None):
        boundary_ids = ctx["boundary_events"].get(node_id, [])
        if not boundary_ids:
            return normal_expr

        alternatives = [normal_expr]
        for boundary_id in boundary_ids:
            if not ctx["boundary_details"].get(boundary_id, {}).get("is_conditional"):
                alternatives.append(build_boundary_expr(
                    boundary_id,
                    ctx,
                    current_proc_id,
                    stop_node=stop_node,
                    visited=set(visited or set())
                ))
        return choice(alternatives)

    def build_conditional_boundary_activity(current_id, inner_ctx, ctx, current_proc_id, stop_node, visited):
        flags = []
        for b_id in ctx["boundary_events"].get(current_id, []):
            details = ctx["boundary_details"].get(b_id, {})
            if details.get("is_conditional"):
                flags.append(clean_name(b_id))

        if not flags:
            return "delta"

        proc_name = f"activity_{clean_name(current_id)}"
        params = ", ".join(["oid: OrderId", "active: Bool"] + [f"{f}_done: Bool" for f in flags])

        def updated_condition_values(triggered_flag, current_values):
            return {k: ("true" if k == triggered_flag else v) for k, v in current_values.items()}

        def inner_successors_expr(node, current_values, current_visited):
            next_nodes = first_successors(node, inner_ctx)
            return choice([
                build_inner_expr(n, current_values, set(current_visited))
                for n in next_nodes
            ])

        def build_inner_expr(current_id, values, current_visited):
            if not current_id: return "delta"
            if current_id in current_visited: return "delta"
            current_visited.add(current_id)

            def wrap_conditional_boundaries(expr, current_values):
                options = [expr]
                for boundary_id in ctx["boundary_events"].get(node_id, []):
                    details = ctx["boundary_details"].get(boundary_id, {})
                    if details.get("is_conditional"):
                        flag_name = clean_name(boundary_id)
                        conditions = details.get("condition_texts", [])
                        guard = parse_condition(" && ".join(conditions))
                        boundary_act = make_node_action(boundary_id, ctx, current_proc_id)
                        cancel = details.get("cancel_activity", True)

                        next_nodes = first_successors(boundary_id, ctx)
                        boundary_tail = choice([
                            build_expr(n, ctx, current_proc_id, stop_node=stop_node, visited=set(visited))
                            for n in next_nodes
                        ])
                        
                        args = ["oid", "false" if cancel else "true"] + [current_values[f] for f in flags]
                        call_proc = f"{proc_name}({', '.join(args)})"
                        
                        options.append(f"({guard}) -> ({boundary_act} . {seq([call_proc, boundary_tail])})")
                return choice(options)

            ntype = inner_ctx["types"].get(current_id)
            if ntype == "endEvent":
                action_expr = make_node_action(current_id, inner_ctx, current_proc_id)
                return wrap_conditional_boundaries(action_expr, values)

            if ntype == "exclusiveGateway":
                next_nodes = first_successors(current_id, inner_ctx)
                branches = []
                for n in next_nodes:
                    cond = inner_ctx["flow_conditions"].get((current_id, n))
                    branch_expr = build_inner_expr(n, values, set(current_visited))
                    if cond:
                        branches.append(f"{cond} -> {seq(['tau', branch_expr])}")
                    else:
                        branches.append(seq(["tau", branch_expr]))
                return wrap_conditional_boundaries(choice(branches), values)

            action_expr = make_node_action(current_id, inner_ctx, current_proc_id)
            raw_name = inner_ctx["nodes"].get(current_id, current_id)
            action_name = clean_name(raw_name if raw_name else current_id)
            next_values = updated_condition_values(action_name, values)
            normal = seq([action_expr, inner_successors_expr(current_id, next_values, current_visited)])
            return wrap_conditional_boundaries(normal, values)

        initial_values = {flag: flag for flag in flags}
        body = choice([
            build_inner_expr(start, initial_values, set())
            for start in inner_ctx["starts"]
        ]) if inner_ctx else "delta"
        sync_state["extra_procs"].append(f"  {proc_name}({params}) = {body};")

        initial_args = ["oid", "true"] + ["false" for _ in flags]
        return f"{proc_name}({', '.join(initial_args)})"

    def build_expr(node_id, ctx, current_proc_id, stop_node=None, visited=None):
        if not node_id or node_id == stop_node:
            return ""

        visited = set(visited or set())
        if node_id in visited:
            return "delta"
        visited.add(node_id)

        ntype = ctx["types"].get(node_id)
        next_nodes = first_successors(node_id, ctx)

        if ntype == "subProcess":
            inner_ctx = ctx["subprocesses"].get(node_id)
            conditional_boundary_ids = [
                boundary_id
                for boundary_id in ctx["boundary_events"].get(node_id, [])
                if ctx["boundary_details"].get(boundary_id, {}).get("is_conditional")
            ]
            if conditional_boundary_ids:
                return build_conditional_boundary_activity(
                    node_id,
                    inner_ctx,
                    ctx,
                    current_proc_id,
                    stop_node,
                    visited,
                )
            sub_logic = build_start_scope(inner_ctx, current_proc_id, visited) if inner_ctx else "delta"
            tail = choice([
                build_expr(n, ctx, current_proc_id, stop_node=stop_node, visited=set(visited))
                for n in next_nodes
            ])
            normal_expr = seq([sub_logic, tail])
            return with_boundary_alternatives(
                node_id,
                normal_expr,
                ctx,
                current_proc_id,
                stop_node=stop_node,
                visited=set(visited),
            )

        if ntype == "endEvent":
            return make_node_action(node_id, ctx, current_proc_id)

        if ntype == "parallelGateway" and len(next_nodes) > 1:
            join = find_join(next_nodes, ctx["flows"])
            sync_state["count"] += 1
            sid = sync_state["count"]
            t_s, t_r, t_c = f"s_start_gw_{sid}", f"r_start_gw_{sid}", f"c_start_gw_{sid}"
            r_join = f"r_sync_join_{sid}"
            c_join = f"c_sync_join_{sid}"
            sync_state["all_sync_actions"].update({t_s, t_r, t_c, r_join, c_join})

            for i, b_start in enumerate(next_nodes):
                b_name = f"gw_{sid}_branch_{i}"
                s_sig = f"s_sync_{sid}_{i}"
                sync_state["all_sync_actions"].add(s_sig)
                b_body = build_expr(
                    b_start,
                    ctx,
                    current_proc_id,
                    stop_node=join,
                    visited=set(visited),
                )
                sync_state["extra_procs"].append(
                    f"  {b_name}(oid: OrderId{params_def}) = {t_r}(oid) . {seq([b_body, f'{s_sig}(oid)'])} . delta;"
                )
                sync_state["init_procs"].append(f"{b_name}(order_id(1){params_init})")

            j_logic = build_expr(join, ctx, current_proc_id, stop_node=stop_node, visited=set(visited))
            sync_state["extra_procs"].append(f"  gw_{sid}_handler(oid: OrderId{params_def}) = {seq([f'{r_join}(oid)', j_logic])};")
            sync_state["init_procs"].append(f"gw_{sid}_handler(order_id(1){params_init})")

            sync_state["rules"].append(f"{t_s} | {' | '.join([t_r] * len(next_nodes))} -> {t_c}")
            s_syncs = [f"s_sync_{sid}_{i}" for i in range(len(next_nodes))]
            sync_state["rules"].append(f"{' | '.join(s_syncs)} | {r_join} -> {c_join}")
            return f"{t_s}(oid) . delta"

        if ntype == "exclusiveGateway" and len(next_nodes) > 1:
            join = find_join(next_nodes, ctx["flows"])
            branch_stop = join if join else stop_node
            branches = []
            for n in next_nodes:
                branch_expr = build_expr(
                    n,
                    ctx,
                    current_proc_id,
                    stop_node=branch_stop,
                    visited=set(visited),
                )
                cond = ctx["flow_conditions"].get((node_id, n))
                if cond:
                    branches.append(f"{cond} -> {seq(['tau', branch_expr])}")
                else:
                    branches.append(seq(["tau", branch_expr]))
            gateway_expr = choice(branches)
            if join:
                tail = build_expr(join, ctx, current_proc_id, stop_node=stop_node, visited=set(visited))
                return seq([gateway_expr, tail])
            return gateway_expr

        action_expr = make_node_action(node_id, ctx, current_proc_id)
        tail = choice([
            build_expr(n, ctx, current_proc_id, stop_node=stop_node, visited=set(visited))
            for n in next_nodes
        ])
        normal_expr = seq([action_expr, tail])

        return with_boundary_alternatives(
            node_id,
            normal_expr,
            ctx,
            current_proc_id,
            stop_node=stop_node,
            visited=set(visited),
        )

    def build_start_scope(ctx, current_proc_id, visited=None):
        starts = ctx["starts"]
        if not starts:
            return "delta"

        start_exprs = []
        for start in starts:
            base_expr = build_expr(start, ctx, current_proc_id, visited=set(visited or set()))

            if start in ctx.get("timer_info", {}):
                timer_info = ctx["timer_info"][start]
                if timer_info["type"] == "duration":
                    delay = parse_duration_to_time(timer_info["value"])
                    start_exprs.append(f"(tau @ {delay}) . {base_expr}")
                elif timer_info["type"] == "cycle":
                    interval = parse_cron_to_interval(timer_info["value"])
                    if interval:
                        sync_state["has_cycle_timer"] = True
                        trigger_act = f"trigger_{clean_name(start)}"
                        sync_state["all_sync_actions"].update({f"s_{trigger_act}", f"r_{trigger_act}", f"c_{trigger_act}"})
                        sync_state["rules"].append(f"s_{trigger_act} | r_{trigger_act} -> c_{trigger_act}")
                        
                        timer_proc_name = f"Timer_{clean_name(start)}"
                        sync_state["extra_procs"].append(
                            f"  {timer_proc_name}(id_num: Pos, t: Real) = (tau @ t) . s_{trigger_act}(order_id(id_num)) . {timer_proc_name}(id_num + 1, t + {interval});"
                        )
                        sync_state["init_procs"].append(f"{timer_proc_name}(1, 0)")
                        
                        start_exprs.append(base_expr)
                    else:
                        start_exprs.append(base_expr)
                else:
                    start_exprs.append(base_expr)
            else:
                start_exprs.append(base_expr)

        return choice(start_exprs)

    main_procs_code = []
    for p_id, ctx in process_contexts.items():
        clean_p_id = clean_name(p_id)
        logic = build_start_scope(ctx, p_id)

        cycle_trigger = None
        for start in ctx["starts"]:
            if start in ctx.get("timer_info", {}):
                if ctx["timer_info"][start]["type"] == "cycle":
                    cycle_trigger = f"trigger_{clean_name(start)}"
                    break

        if cycle_trigger:
            instance_name = f"{clean_p_id}_instance"
            factory_name = f"{clean_p_id}_factory"

            factory_body = f"r_{cycle_trigger}(order_id(id_num)) . "
            if vars_list:
                sum_vars = ", ".join([f"{v}: Int" for v in vars_list])
                guards = " && ".join([f"({v} >= 0 && {v} <= 10)" for v in vars_list])
                factory_body += f"(sum {sum_vars} . ({guards}) -> ( {instance_name}(order_id(id_num){params_call}) . {factory_name}(id_num + 1) ))"
            else:
                factory_body += f"( {instance_name}(order_id(id_num){params_call}) . {factory_name}(id_num + 1) )"

            main_procs_code.append(f"  {instance_name}(oid: OrderId{params_def}) = {logic} . delta;")
            main_procs_code.append(f"  {factory_name}(id_num: Pos) = {factory_body};")

            sync_state["init_procs"].append(f"{factory_name}(1)")
            sync_state["has_timer"] = True
        else:
            init_call = f"{clean_p_id}(order_id(1){params_call})"
            if vars_list:
                sum_vars = ", ".join([f"{v}: Int" for v in vars_list])
                guards = " && ".join([f"({v} >= 0 && {v} <= 10)" for v in vars_list])
                init_call = f"(sum {sum_vars} . ({guards}) -> {init_call})"

            main_procs_code.append(f"  {clean_p_id}(oid: OrderId{params_def}) = {logic};")
            sync_state["init_procs"].append(init_call)

    final_declarations = sorted(sync_state["used_actions"] | sync_state["all_sync_actions"])
    forbidden_prefixes = ("s_", "r_", "s_sync")
    allow_acts = [a for a in final_declarations if not a.startswith(forbidden_prefixes)]
    init_body = " || ".join(sync_state["init_procs"]) if sync_state["init_procs"] else "delta"

    if sync_state["rules"]:
        # 将 rules 列表转化为集合 (set) 进行去重，再转化为列表排序，保证输出稳定性
        unique_rules = sorted(list(set(sync_state["rules"])))
        rules_str = ", ".join(unique_rules)
        init_code = f"""allow({{{', '.join(sorted(allow_acts))}}},
    comm({{{rules_str}}},
      {init_body}
    )
  )"""
    else:
        init_code = f"""allow({{{', '.join(sorted(allow_acts))}}},
    {init_body}
  )"""

    if sync_state["has_timer"] or vars_list:
        mcrl2_code = f"""% Auto-generated mCRL2 with Collaboration & Parallel Support & Timed Events & Data
sort OrderId = struct order_id(pid: Pos);

act
  {', '.join(final_declarations)} : OrderId;

proc
{chr(10).join(main_procs_code)}
{chr(10).join(sync_state['extra_procs'])}

init
  {init_code};
"""
    else:
        mcrl2_code = f"""% Auto-generated mCRL2 with Collaboration & Parallel Support
sort OrderId = struct order_id(pid: Pos);

act
  {', '.join(final_declarations)} : OrderId;

proc
{chr(10).join(main_procs_code)}
{chr(10).join(sync_state['extra_procs'])}

init
  {init_code};
"""
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(mcrl2_code)

    for warning in sync_state["warnings"]:
        print(f"⚠️ {warning}")
    print(f"✅ 转换完成！输出至: {output_filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 BPMN 转换为 mCRL2 模型")
    parser.add_argument("input_file", nargs="?", default="", help="BPMN 文件的路径 (可选)")
    parser.add_argument("output_file", nargs="?", default="", help="输出的 mCRL2 文件路径 (可选)")
    parser.add_argument("--disable-timer", action="store_true", help="禁用定时器特殊建模（将定时器视为普通节点）")
    
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    
    if args.input_file:
        input_file = Path(args.input_file)
    else:
        input_file = project_root / "samples" / "sample3" / "camunda" / "pizza-collaboration.bpmn"
        
    if args.output_file:
        output_file = Path(args.output_file)
    else:
        output_file = project_root / "samples" / "sample3" / "mcrl2" / "pizza-collaboration_output.mcrl2"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 核心调用，将命令行开关的状态取反后传入
    convert_bpmn_to_mcrl2(str(input_file), str(output_file), enable_timer=not args.disable_timer)
