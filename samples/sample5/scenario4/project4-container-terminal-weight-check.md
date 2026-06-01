# Project 4: Container Terminal Weight Check

## Scenario

The original `all.bpmn` lets the Container Terminal execute `load CTN` (`Activity_0x24wd2`) immediately after the manifest, ship-arrival message, and outbound container are received. This misses the VGM-style safety check that should decide whether the container is allowed to be loaded.

This project extracts that local behavior into a small collaboration with two pools:

- `Container Terminal`: receives weight data, performs safety weighing, and decides whether to load.
- `Environment`: supplies the weight data and receives a rejection warning when the container is overweight.

## BPMN Optimization

The new model is `bpmn/container-terminal-weight-check.bpmn`.

The optimized process adds:

- `Weight data received`: an environment message representing the available container weight.
- `safety weighing`: the explicit validation task before loading.
- `weight within VGM limit?`: an exclusive gateway with two data guards.
- `weight <= max_limit`: compliant branch, then `load CTN`.
- `weight > max_limit`: overweight branch, then `send reject loading warning` and stop the loading operation.

## mCRL2 Data View

The converter extracts `weight` and `max_limit` from the BPMN guard expressions and generates them as `Int` process parameters. The initial process enumerates bounded values for both variables, so both the compliant and overweight branches are present in the explored state space.

Expected generated guard shape:

```mcrl2
(weight <= max_limit) -> tau . load_ctn(oid)
+
(weight > max_limit) -> tau . s_reject_loading_warning_to_environment(oid)
```

## Verification Commands

Run from the repository root:

```bash
python scripts/bpmn2mcrl2.py \
  samples/sample4/bpmn/container-terminal-weight-check.bpmn \
  samples/sample4/mcrl2/container-terminal-weight-check_output.mcrl2

mcrl22lps \
  samples/sample4/mcrl2/container-terminal-weight-check_output.mcrl2 \
  samples/sample4/mcrl2/container-terminal-weight-check.lps

lps2lts \
  samples/sample4/mcrl2/container-terminal-weight-check.lps \
  samples/sample4/mcrl2/container-terminal-weight-check.lts

ltsinfo samples/sample4/mcrl2/container-terminal-weight-check.lts
```

Additional reachability checks:

```bash
lps2pbes -f samples/sample4/mcf/project4_load_reachable.mcf \
  samples/sample4/mcrl2/container-terminal-weight-check.lps \
  samples/sample4/mcrl2/project4_load_reachable.pbes
pbes2bool samples/sample4/mcrl2/project4_load_reachable.pbes

lps2pbes -f samples/sample4/mcf/project4_reject_reachable.mcf \
  samples/sample4/mcrl2/container-terminal-weight-check.lps \
  samples/sample4/mcrl2/project4_reject_reachable.pbes
pbes2bool samples/sample4/mcrl2/project4_reject_reachable.pbes
```

Both checks should return `true`.
