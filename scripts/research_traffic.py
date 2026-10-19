"""Conservative metered-transfer checks; never downloads or changes proxy settings."""
import os,re,subprocess
LIMIT=1_000_000_000

def proxy_state():
    environment=any(value for key,value in os.environ.items() if key.upper() in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'))
    detected=False;checked=False
    try:
        result=subprocess.run(['/usr/sbin/scutil','--proxy'],capture_output=True,text=True,timeout=3)
        checked=result.returncode==0
        detected=bool(re.search(r'(?:HTTPEnable|HTTPSEnable|SOCKSEnable|ProxyAutoConfigEnable)\s*:\s*1',result.stdout))
    except (OSError,subprocess.SubprocessError):pass
    return {'proxy_detected':environment or detected,'system_check_completed':checked,'metered_assumed':environment or detected or not checked}

def check_size(size,used):
    if type(size) is not int or size<=0:raise ValueError('下载大小未知或无效：先核实大小；集中告知来源/文件名/预计大小/目标路径，等待用户手动下载或明确安排，未提交任务')
    if size>LIMIT:raise ValueError('下载超过1GB：停止提交；请用户关闭VPN并集中手动下载，等待放好后再导入')
    if used+size>LIMIT:raise ValueError('累计申报下载将超过1GB：停止提交并集中交接用户手动下载；不自动重试或重置预算')
