import json
import os
from pathlib import Path
from models.project import Project

def save(project, path):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps({'format': 'juno-sequencer', 'version': 1, **project.data()}, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)

def load(path):
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    if d.get('format') != 'juno-sequencer' or d.get('version') != 1:
        raise ValueError('未対応のプロジェクト形式です')
    return Project.from_data(d)
