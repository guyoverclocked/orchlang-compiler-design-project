#!/usr/bin/env bash
# Fetch every source of the real-workflow corpus at its pinned revision into
# bench/.cache/real/ (ignored by git).  verify_sources.py and
# agentdojo_canaries.py read from there.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cache="$here/../.cache/real"
mkdir -p "$cache"

fetch() {  # fetch <dir> <repo> <commit> [sparse path]
  local dir="$cache/$1" repo="$2" commit="$3" sparse="${4:-}"
  if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD)" = "$commit" ]; then return; fi
  rm -rf "$dir"; mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" remote add origin "https://github.com/$repo"
  if [ -n "$sparse" ]; then
    git -C "$dir" config core.sparseCheckout true
    echo "$sparse" > "$dir/.git/info/sparse-checkout"
  fi
  git -C "$dir" fetch -q --depth 1 origin "$commit"
  git -C "$dir" checkout -q FETCH_HEAD
}

fetch anthropic-cookbook anthropics/anthropic-cookbook 813fbeec03cdedfda7808529438d1c7af71f26eb patterns/agents/
fetch langgraph langchain-ai/langgraph 23961cff61a42b52525f3b20b4094d8d2fba1744 docs/docs/tutorials/
fetch agentdojo ethz-spylab/agentdojo 089ed468cf3ed0322acc66b0211f26d9d90dbf60

# LangChain Hub prompts, by commit hash.
mkdir -p "$cache/hub"
python3 - "$here/manifest.json" "$cache/hub" <<'PY'
import json, os, sys, urllib.request
manifest, out = sys.argv[1], sys.argv[2]
for c in json.load(open(manifest))['candidates']:
    for name, commit in c['source'].get('hub_prompts', {}).items():
        path = os.path.join(out, name.replace('/', '__') + '.json')
        if os.path.exists(path):
            continue
        url = 'https://api.smith.langchain.com/commits/%s/%s' % (name, commit)
        data = json.load(urllib.request.urlopen(url))
        assert data['commit_hash'] == commit, (name, data['commit_hash'])
        json.dump(data, open(path, 'w'), indent=1)
PY
echo "sources in $cache"
