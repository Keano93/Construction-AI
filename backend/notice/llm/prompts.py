"""Versioned prompt files.

Layout: prompts/<agent>/<task>.v<N>.md

    ---
    id: notice_agent.classify
    version: 1
    description: ...
    ---
    ## system
    ...
    ## user
    ... {{variable}} ...

The highest version is used unless a version is pinned. The prompt id + version
is stored on every AgentRun so outputs can be traced back to the exact prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import get_settings

_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class Prompt:
    id: str
    version: int
    system: str
    user: str
    path: str

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"

    def render(self, **variables: object) -> tuple[str, str]:
        def sub(template: str) -> str:
            def repl(m: re.Match) -> str:
                key = m.group(1)
                if key not in variables:
                    raise KeyError(f"Prompt {self.ref} needs variable '{key}'")
                return str(variables[key])

            return _VAR.sub(repl, template)

        return sub(self.system), sub(self.user)


def _parse(path: Path) -> Prompt:
    raw = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"{path}: missing front matter")
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    body = m.group(2)
    sections = re.split(r"^## (system|user)\s*$", body, flags=re.M)
    parts = {sections[i]: sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    if "system" not in parts or "user" not in parts:
        raise ValueError(f"{path}: needs '## system' and '## user' sections")
    return Prompt(id=meta["id"], version=int(meta["version"]), system=parts["system"], user=parts["user"], path=str(path))


@lru_cache
def load_prompt(agent: str, task: str, version: int | None = None) -> Prompt:
    root = get_settings().prompts_dir / agent
    candidates = sorted(
        (int(m.group(1)), p)
        for p in root.glob(f"{task}.v*.md")
        if (m := re.search(r"\.v(\d+)\.md$", p.name))
    )
    if not candidates:
        raise FileNotFoundError(f"No prompt files for {agent}/{task} in {root}")
    if version is None:
        return _parse(candidates[-1][1])
    for v, p in candidates:
        if v == version:
            return _parse(p)
    raise FileNotFoundError(f"Prompt {agent}/{task} v{version} not found")
