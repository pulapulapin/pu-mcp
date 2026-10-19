"""Shared task-direction selection; no fiction file reads or manuscript writes."""
def resume_task(self,project,session_id='',inferred=None):
    inferred=inferred or {'label':None,'instruction':None}
    checkpoint=self.store.checkpoint(project)
    resolved=self.conversations.resolve(project,session_id)
    backup=resolved['backup'];selection=resolved['selection']
    required=selection['status']=='selection_required'
    context=backup.get('task_context') if backup else None
    activity=self.settings['project_states'].get(project,'active')
    mode='task_selection_required' if required else 'session_backup' if backup else 'checkpoint' if checkpoint else 'json_task_inference' if inferred['instruction'] else 'unassigned'
    has_saved_task=bool(backup or checkpoint)
    stage=context['stage'] if context else None if required or has_saved_task else inferred['label']
    if checkpoint and not backup and not required:selection['warnings'].append('旧检查点无任务阶段，阶段未知；项目阶段单独返回')
    if backup and checkpoint and checkpoint['task']!=backup['task']:selection['warnings'].append('会话任务与旧检查点不同，采用选定快照；检查点仅供历史核对')
    if context and inferred['label'] and context['stage']!=inferred['label']:selection['warnings'].append('任务阶段与项目配置阶段不同，任务阶段采用快照；project_stage仅供核对')
    return {'project':project,'path':str(self.project(project)),'checkpoint':checkpoint,'session_backup':backup,
        'task':None if required else backup['task'] if backup else checkpoint['task'] if checkpoint else inferred['instruction'],
        'activity':activity,
        'automatic_development_allowed':activity!='paused' and not required and (bool(context and context['state']=='active' and not selection['historical']) if backup else not has_saved_task and bool(inferred['instruction'])),
        'stage':stage,'stage_source':'session_backup' if context else 'unknown' if required or has_saved_task else 'json_project_state' if inferred['label'] else 'unknown',
        'project_stage':inferred['label'],'project_stage_source':'json_project_state' if inferred['label'] else 'unavailable',
        'task_id':context['task_id'] if context else None,'task_state':context['state'] if context else None,
        'direction_revision':context['direction_revision'] if context else None,'task_selection':selection,
        'next_step':None if required else backup['next_step'] if backup else checkpoint['next_step'] if checkpoint else inferred['instruction'],
        'resume_mode':mode,
        'notice':'按明确方向恢复同源任务/阶段/下一步；未知或并列不猜测，旧方向或非active不自动推进；摘要非Canon。'}
