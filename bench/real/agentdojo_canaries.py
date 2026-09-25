"""Which AgentDojo tool responses carry an injection vector.

For each selected v1 user task, run its ground truth with a canary string in
every injection vector (AgentDojo's own mechanism, as in TaskSuite.check) and
report which vectors each tool response contains.  A response that contains
one is labelled untrusted in manifest.json; this is the label rule of
PROTOCOL.md section 3 for AgentDojo, and it is AgentDojo's, not ours.

Needs AgentDojo at the pinned commit:
    bash bench/real/fetch_sources.sh
    python3 -m venv bench/.cache/real/venv
    bench/.cache/real/venv/bin/pip install -e bench/.cache/real/agentdojo
    bench/.cache/real/venv/bin/python bench/real/agentdojo_canaries.py \
        > bench/real/agentdojo_canaries.json
"""
import json, sys
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline

SELECT = {'banking': [0,1,2,3,4], 'slack': [0,1,2,3,4], 'travel': [0,1,2,3,4], 'workspace': [0,1,2,3,5]}
out = {}
for suite_name, ids in SELECT.items():
    suite = get_suite('v1', suite_name)
    defaults = suite.get_injection_vector_defaults()
    canaries = {inj: f"---CANARY_{inj}---" for inj in defaults}
    env = suite.load_and_inject_default_environment(canaries)
    for i in ids:
        task = suite.get_user_task_by_id(f'user_task_{i}')
        pipe = GroundTruthPipeline(task)
        runtime = FunctionsRuntime(suite.tools)
        _, _, _, messages, _ = pipe.query(task.PROMPT, runtime, env.copy(deep=True))
        calls = []
        for m in messages:
            if m['role'] == 'tool':
                content = m['content'] if isinstance(m['content'], str) else json.dumps(m['content'], default=str)
                text = str(content)
                found = sorted(inj for inj, c in canaries.items() if c in text)
                calls.append({'function': m['tool_call'].function, 'args': m['tool_call'].args,
                              'injection_vectors': found, 'response_bytes': len(text.encode())})
        out[f'ad-{suite_name}-{i}'] = {'prompt': task.PROMPT, 'calls': calls}
json.dump(out, sys.stdout, indent=1, default=str)
