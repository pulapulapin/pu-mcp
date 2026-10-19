"""PuCatch public v1 HTTP only; no provider imports or filesystem access."""
import json,re
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('拒绝采集服务重定向')
class ProviderError(ValueError):
 def __init__(self,code,retryable=False):
  self.code=code;self.retryable=retryable;super().__init__('PuCatch '+code+'；未自动重试，请核对任务或服务状态')
def request(base,route,payload=None,headers=None):
 data=json.dumps(payload).encode() if payload is not None else None
 req=Request(base+route,data=data,headers={'Content-Type':'application/json',**(headers or {})},method='POST' if payload is not None else 'GET')
 try:
  with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=30) as response:
   raw=response.read(1024*1024+1)
   if len(raw)>1024*1024:raise ValueError('采集服务响应超过1MiB')
   value=json.loads(raw)
   if not isinstance(value,dict):raise ValueError('采集服务响应格式无效')
   return value
 except HTTPError as exc:
  try:error=json.loads(exc.read(65536)).get('error',{});code=error.get('code','HTTP_ERROR');retry=error.get('retryable') is True
  except Exception:code='HTTP_ERROR';retry=False
  if not isinstance(code,str) or not re.fullmatch('[A-Z_]{1,80}',code):code='HTTP_ERROR'
  exc.close()
  raise ProviderError(code,retry) from None
 except (OSError,TimeoutError):raise ProviderError('CONNECTION_UNAVAILABLE') from None
