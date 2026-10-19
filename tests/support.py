"""Synthetic fixtures: never reads the author's projects or changes Canon."""
import json
from pathlib import Path

def create_story(path,project_id='sample-story'):
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    values={
      'story-contract':{'id':project_id,'mode':'novel','title':'合成测试作品','genre':'原创','logline':'仅供工程验证','core_conflict':'','invariants':['测试不确认真实作品设定']},
      'world':{'rules':[{'id':'sample-rule','rule':'合成规则','status':'confirmed'},{'id':'candidate-rule','rule':'候选规则','status':'proposed'}]},
      'characters':{'characters':[]},'timeline':{'events':[]},'chapters':{'chapters':[]}}
    for name,value in values.items():(path/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return path
