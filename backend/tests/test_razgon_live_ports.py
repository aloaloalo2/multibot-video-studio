"""Independent previews must survive collisions and concurrent requests without rendering."""
import concurrent.futures
import json
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import razgon_live as live
import store


@unittest.skipUnless(shutil.which('node'), 'Node required for real live-preview servers')
class LivePortTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        (self.root/'tools').mkdir()
        source=Path(__file__).resolve().parents[2]/'razgon-2d-studio'/'tools'/'live.mjs'
        shutil.copy2(source,self.root/'tools'/'live.mjs')
        (self.root/'live.html').write_text('<html>Live preview</html>')
        self.projects={}
        for pid in ('first','second'):
            folder=self.root/pid;(folder/'scenes').mkdir(parents=True)
            (folder/'config.json').write_text('{}')
            (folder/'scenes'/(pid+'.js')).write_text('// '+pid)
            self.projects[pid]={'id':pid,'path':folder}
        self.port=live._free_port(0)
        original_saved=live._saved_port
        for name,func in (
            ('load_project',lambda pid:self.projects[pid]),
            ('razgon_link',lambda p:{'razgon_root':str(self.root),'project':str(p['path'])})):
            mock=patch.object(store,name,side_effect=func);mock.start();self.addCleanup(mock.stop)
        mock=patch.object(live,'_saved_port',side_effect=lambda p,preferred:original_saved(p,self.port))
        mock.start();self.addCleanup(mock.stop)
        self.children=[]
        original_spawn=subprocess.Popen
        def spawn(*args,**kwargs):
            child=original_spawn(*args,**kwargs)
            if Path(args[0][0]).name=='node':self.children.append(child)
            return child
        # Cleanup only the Node children started by this fixture.
        def cleanup():
            for child in self.children:
                if child.poll() is None:child.terminate()
                child.wait(timeout=5)
        self.addCleanup(cleanup)
        mock=patch.object(live.subprocess,'Popen',side_effect=spawn)
        mock.start();self.addCleanup(mock.stop)

    def read(self,url):
        with urllib.request.urlopen(url,timeout=2) as response:return response.read()

    def test_collision_keeps_other_project_alive_and_remembers_alternative(self):
        first=live.start('first')
        second=live.start('second',restart=True)
        self.assertNotEqual(first['url'],second['url'])
        for pid,result in [('first',first),('second',second)]:
            base=result['url'].removesuffix('/live.html')
            health=json.loads(self.read(base+'/__health'))
            self.assertEqual(health['project'],str(self.projects[pid]['path']))
            self.assertEqual(json.loads(self.read(base+'/__manifest')),['/project/scenes/'+pid+'.js'])
            self.assertIn(b'Live preview',self.read(result['url']))
            self.assertEqual(live.status(pid)['url'],result['url'])
            self.assertTrue(live.status(pid)['running'])
            self.assertEqual(live.start(pid),result)
        self.assertEqual(len(self.children),2)

    def test_concurrent_opens_share_one_server(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:live.start('first'),range(3)))
        self.assertTrue(all(result==results[0] for result in results))
        self.assertEqual(len(self.children),1)

    def test_restart_only_replaces_its_own_server_and_retains_url(self):
        first=live.start('first');old=self.children[0]
        restarted=live.start('first',restart=True)
        self.assertEqual(first,restarted)
        self.assertIsNotNone(old.poll())
        self.assertTrue(live.status('first')['running'])

    def test_external_bind_race_retries_without_accepting_foreign_health(self):
        first=live.start('first')
        fallback=live._free_port(self.port)
        with patch.object(live,'_free_port',side_effect=[self.port,fallback]):
            second=live.start('second')
        self.assertNotEqual(first['url'],second['url'])
        self.assertTrue(live.status('first')['running'])
        self.assertTrue(live.status('second')['running'])

    def test_non_http_listener_is_preserved_even_on_restart(self):
        with socket.socket() as other:
            other.bind(('127.0.0.1',self.port));other.listen()
            # An unrelated program's listener has no preview health endpoint.
            with patch.object(live,'_health',side_effect=lambda port:None if port==self.port else original_health(port)):
                result=live.start('first',restart=True)
            self.assertNotIn(':'+str(self.port)+'/',result['url'])
            self.assertEqual(other.getsockname()[1],self.port)

    def test_invalid_saved_port_does_not_break_reopening(self):
        path=self.projects['first']['path']/'build'/'live-server.json';path.parent.mkdir()
        for value in ('broken','[]','{"port":true}','{"port":-1}','{"port":99999}'):
            path.write_text(value)
            self.assertEqual(live.link(self.projects['first'])['port'],self.port)


original_health=live._health

if __name__=='__main__':unittest.main()
