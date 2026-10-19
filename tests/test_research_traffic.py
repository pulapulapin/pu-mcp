import os,sys,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from research_traffic import proxy_state,check_size
class TrafficTests(unittest.TestCase):
 def test_environment_and_system_proxy_detection_without_credentials(self):
  with patch.dict(os.environ,{'HTTPS_PROXY':'http://private:secret'+'@example.org:8080'},clear=True),patch('research_traffic.subprocess.run',return_value=subprocess.CompletedProcess([],0,'<dictionary> {}','')):
   state=proxy_state();self.assertTrue(state['proxy_detected']);self.assertNotIn('secret',str(state))
  with patch.dict(os.environ,{},clear=True),patch('research_traffic.subprocess.run',return_value=subprocess.CompletedProcess([],0,'HTTPSEnable : 1','')):self.assertTrue(proxy_state()['proxy_detected'])
 def test_failed_proxy_check_is_conservative(self):
  with patch.dict(os.environ,{},clear=True),patch('research_traffic.subprocess.run',side_effect=OSError()):self.assertTrue(proxy_state()['metered_assumed'])
 def test_size_budget_boundaries(self):
  check_size(100,999_999_900)
  for size,used in [(101,999_999_900),(None,0),(True,0),(1_000_000_001,0)]:
   with self.subTest(size=size),self.assertRaises(ValueError):check_size(size,used)
