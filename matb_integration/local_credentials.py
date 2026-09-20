"""Server-only, lazy credential lookup. Never exports settings into the environment."""
from pathlib import Path
import os
import re

_ALIASES = {'openai': ('OPENAI_API_KEY',), 'jev': ('JEV_AI_API_KEY', 'JEV_API_KEY')}


def local_env_path(repository_root: Path) -> Path:
    explicit = os.getenv('MATB_LOCAL_ENV_FILE')
    if explicit:
        return Path(explicit).expanduser()
    local = repository_root / '.env.local'
    if local.exists():
        return local
    # Linked worktrees may share the main checkout's ignored credential file.
    # Consult Git metadata only; do not search arbitrary ancestor directories.
    gitfile = repository_root / '.git'
    if gitfile.is_file():
        try:
            pointer = gitfile.read_text(encoding='utf-8').strip()
            if pointer.startswith('gitdir: '):
                metadata = (repository_root / pointer[8:]).resolve()
                common = (metadata / (metadata / 'commondir').read_text(encoding='utf-8').strip()).resolve()
                if common.name == '.git':
                    return common.parent / '.env.local'
        except (OSError, UnicodeError):
            pass
    return local


def get_api_key(provider: str, *, repository_root: Path | None = None) -> str | None:
    """Process keys win; then the selected local file. Only allowlisted keys load.

    File key names are case-insensitive. Values are literal: no shell expansion,
    interpolation, escape evaluation, dotenv side effects, logging, or network.
    """
    if provider not in _ALIASES:
        raise ValueError('unsupported credential provider')
    aliases = _ALIASES[provider]
    for name in aliases:
        value = os.getenv(name) or os.getenv(name.lower())
        if value and value.strip():
            return value.strip()
    path = local_env_path(repository_root or Path(__file__).resolve().parents[1])
    try:
        with path.open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            return None
        text = raw.decode('utf-8-sig')
    except (OSError, UnicodeError):
        return None
    selected = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, sep, value = line.partition('=')
        name = name.strip().upper()
        if not sep or name not in aliases:
            continue
        value = value.strip()
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end+1:].strip() and not value[end+1:].lstrip().startswith('#')):
                continue
            value = value[1:end]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
        if value and not any(ord(c) < 32 for c in value):
            selected[name] = value
    return next((selected[name] for name in aliases if name in selected), None)
