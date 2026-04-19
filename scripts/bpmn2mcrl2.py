import xml.etree.ElementTree as ET
import re
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


def convert_bpmn_to_mcrl2(bpmn_filepath, output_filepath):
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

    def collect_scope(scope_elem):
        ctx = {
            "nodes": {},
            "types": {},
            "starts": [],
            "flows": {},
            "flow_names": {},
            "subprocesses": {},
            "boundary_events": {},
            "event_definitions": {},
        }

        for elem in list(scope_elem):
            tag = node_type(elem)
            if tag in FLOW_NODE_TYPES and "id" in elem.attrib:
                eid = elem.attrib["id"]
                ctx["nodes"][eid] = elem.attrib.get("name", eid)
                ctx["types"][eid] = tag
                ctx["event_definitions"][eid] = event_definition_types(elem)

                if tag == "startEvent":
                    ctx["starts"].append(eid)
                elif tag == "subProcess":
                    ctx["subprocesses"][eid] = collect_scope(elem)
                    if elem.find("bpmn:multiInstanceLoopCharacteristics", ns) is not None:
                        sync_state["warnings"].append(
                            f"subProcess {eid} contains multiInstanceLoopCharacteristics; "
                            "converted as a single instance."
                        )
                elif tag == "boundaryEvent":
                    attached_to = elem.attrib.get("attachedToRef")
                    if attached_to:
                        ctx["boundary_events"].setdefault(attached_to, []).append(eid)

            elif tag == "sequenceFlow":
                src = elem.attrib.get("sourceRef")
                tgt = elem.attrib.get("targetRef")
                if src and tgt:
                    ctx["flows"].setdefault(src, []).append(tgt)
                    ctx["flow_names"][(src, tgt)] = elem.attrib.get("name", "")

        return ctx

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
            return make_event_action(node_id, ctx, prefix=prefix)

        if ntype == "startEvent":
            defs = ctx["event_definitions"].get(node_id, [])
            if defs:
                return make_event_action(node_id, ctx, prefix="start")
            return ""

        if node_id in sync_state["exact_msg_nodes"]:
            role, m_name = sync_state["exact_msg_nodes"][node_id]
            action_name = f"{role}_{m_name}"
            sync_state["used_actions"].add(action_name)
            return f"{action_name}(oid)"

        raw_name = ctx["nodes"].get(node_id, "")
        action_name = clean_name(raw_name if raw_name else node_id)
        matched_msg = False

        def get_core(name):
            return name.replace("send_", "").replace("recv_", "").replace("receive_", "")

        for msg in sync_state["messages"]:
            m_name = msg["name"]
            core_m = get_core(m_name)
            match_str = core_m if core_m else m_name

            if match_str and match_str in action_name:
                if current_proc_id == msg["src_proc"]:
                    action_name = f"s_{m_name}"
                    matched_msg = True
                    break
                if current_proc_id == msg["tgt_proc"]:
                    action_name = f"r_{m_name}"
                    matched_msg = True
                    break

        if matched_msg or ntype in TASK_NODE_TYPES:
            sync_state["used_actions"].add(action_name)
            return f"{action_name}(oid)"

        return ""

    def build_start_scope(ctx, current_proc_id, visited=None):
        starts = ctx["starts"]
        if not starts:
            return "delta"
        return choice([
            build_expr(start, ctx, current_proc_id, visited=set(visited or set()))
            for start in starts
        ])

    def build_boundary_expr(boundary_id, ctx, current_proc_id, stop_node=None, visited=None):
        boundary_action = make_node_action(boundary_id, ctx, current_proc_id)
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
            alternatives.append(build_boundary_expr(
                boundary_id,
                ctx,
                current_proc_id,
                stop_node=stop_node,
                visited=set(visited or set()),
            ))
        return choice(alternatives)

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
                    f"  {b_name}(oid: OrderId) = {t_r}(oid) . {seq([b_body, f'{s_sig}(oid)'])} . delta;"
                )
                sync_state["init_procs"].append(f"{b_name}(order_id(1))")

            j_logic = build_expr(join, ctx, current_proc_id, stop_node=stop_node, visited=set(visited))
            sync_state["extra_procs"].append(f"  gw_{sid}_handler(oid: OrderId) = {r_join}(oid) . {j_logic};")
            sync_state["init_procs"].append(f"gw_{sid}_handler(order_id(1))")

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

    main_procs_code = []
    for process in root.findall(".//bpmn:process", ns):
        p_id = process.attrib.get("id", "Process")
        clean_p_id = clean_name(p_id)
        ctx = collect_scope(process)
        logic = build_start_scope(ctx, p_id)
        main_procs_code.append(f"  {clean_p_id}(oid: OrderId) = {logic};")
        sync_state["init_procs"].append(f"{clean_p_id}(order_id(1))")

    final_declarations = sorted(sync_state["used_actions"] | sync_state["all_sync_actions"])
    forbidden_prefixes = ("s_", "r_", "s_sync")
    allow_acts = [a for a in final_declarations if not a.startswith(forbidden_prefixes)]
    init_body = " || ".join(sync_state["init_procs"]) if sync_state["init_procs"] else "delta"

    if sync_state["rules"]:
        init_code = f"""allow({{{', '.join(sorted(allow_acts))}}},
    comm({{{', '.join(sync_state['rules'])}}},
      {init_body}
    )
  )"""
    else:
        init_code = f"""allow({{{', '.join(sorted(allow_acts))}}},
    {init_body}
  )"""

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
    project_root = Path(__file__).resolve().parent.parent
    input_file = project_root / "samples" / "sample1" / "camunda" / "message_cossitence.bpmn"
    output_file = project_root / "samples" / "sample1" / "mcrl2" / "message_cossitence_output.mcrl2"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    convert_bpmn_to_mcrl2(str(input_file), str(output_file))
