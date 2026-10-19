"""Optional loopback JSON API. Never auto-started by the MCP server."""
import argparse,json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from knowledge_api import execute,workspace
from research_workspace import ResearchWorkspace
MAX_REQUEST=1_200_000

def make_server(port=8791):
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def reply(self,status,body):
   raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  def do_POST(self):
   allowed={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
   if self.headers.get('Host') not in allowed or self.headers.get('Origin') or self.headers.get('Transfer-Encoding'):
    return self.reply(403,{'ok':False,'error':'仅限本机非浏览器JSON调用'})
   try:
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=MAX_REQUEST:raise ValueError('请求体须1–1200000字节')
    if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('须application/json')
    prefix='/api/v1/knowledge/'
    if not self.path.startswith(prefix):raise ValueError('未知API路径')
    body=json.loads(self.rfile.read(length))
    if not isinstance(body,dict):raise ValueError('参数须JSON对象')
    result=execute(workspace(),self.path[len(prefix):],body)
    self.reply(200,{'ok':True,'result':result})
   except (ValueError,TypeError,KeyError,OSError) as exc:self.reply(400,{'ok':False,'error':str(exc)[:2000]})
 return ThreadingHTTPServer(('127.0.0.1',port),Handler)
def main():
 parser=argparse.ArgumentParser(description='PuKnowledge本机知识JSON API');parser.add_argument('--port',type=int,default=8791);parser.add_argument('--config');args=parser.parse_args()
 if args.config:
  import os
  from pathlib import Path
  selected=str(Path(args.config).expanduser().resolve());os.environ['PUKNOWLEDGE_CONFIG']=selected;os.environ['NOVEL_WORKBENCH_CONFIG']=selected
 server=make_server(args.port)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
 return 0
if __name__=='__main__':raise SystemExit(main())
