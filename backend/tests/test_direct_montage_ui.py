"""Direct montage stays editable while the source voice/transcript page remains available."""
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'engine' / 'tests'))
import preview_js


@unittest.skipUnless(shutil.which('node'), 'node required')
class DirectMontageUITest(unittest.TestCase):
    def test_empty_projects_open_the_combined_planning_and_montage_workspace(self):
        prelude = "const state={channel:{id:'c',settings:{plan_mode:'direct'}},channels:[]};"
        result = preview_js.run(['projectPlanMode', 'directMontage', 'filmClips', 'projectAnimated', 'editorUnlocked'], """
            console.log(JSON.stringify([
              editorUnlocked({channel_id:'c',tracks:[]}),
              editorUnlocked({channel_id:'c',plan_mode:'director',tracks:[]}),
              editorUnlocked({plan_mode:'director',tracks:[{clips:[{id:'f',kind:'image'}]}]}),
              editorUnlocked({plan_mode:'director',tracks:[{clips:[{id:'v',kind:'audio'}]}]}),
              editorUnlocked({production:{plan_mode:'direct'},tracks:[]}),
              editorUnlocked(null)
            ]));
        """, prelude)
        self.assertEqual(result, [True, True, True, True, True, False])

    def test_legacy_mode_opens_combined_editor_without_changing_plan_mode(self):
        prelude = "const state={channel:{id:'c',settings:{}},channels:[]};"
        result = preview_js.run(['projectPlanMode', 'directMontage', 'filmClips', 'projectAnimated', 'editorUnlocked'], """
            const p={channel_id:'c',scene_groups:[{role:'overlay',clip_ids:['plate']}],
              tracks:[{clips:[{id:'plate',kind:'image'}]}]};
            console.log(JSON.stringify([projectPlanMode(p),editorUnlocked(p),
              directMontage({plan_mode:'unsupported',tracks:[]})]));
        """, prelude)
        self.assertEqual(result, ['director', True, False])

    def test_project_source_is_selected_by_mode_and_other_channel_is_not_inherited(self):
        prelude = "const state={channel:{id:'other',settings:{plan_mode:'direct'}},channels:[]};"
        result = preview_js.run(['projectPlanMode', 'directMontage', 'sourceForProject'], """
          const data={source:{script:'source'},plan:{script:'plan',frames:[{}]}};
          console.log(JSON.stringify([
            sourceForProject(data,{plan_mode:'direct'}).script,
            sourceForProject(data,{plan_mode:'director'}).script,
            projectPlanMode({channel_id:'not-selected'}),
            sourceForProject({plan:data.plan},{plan_mode:'direct'}).script
          ]));
        """, prelude)
        self.assertEqual(result, ['source', 'plan', 'director', 'plan'])

    def test_direct_source_page_with_audio_does_not_require_frame_plan(self):
        prelude = """
          const nodes={};const $=id=>nodes[id]??=( {textContent:'',attrs:{},
            setAttribute(k,v){this.attrs[k]=v},classList:{toggle(){}},replaceChildren(){}} );
          const state={project:{id:'p',plan_mode:'direct'},plan:{timing:{status:'audio_synced'},frames:[]},
            view:'plan',channels:[]};
          let rendered='';function renderInlineEpisodeDraft(){return false}function renderPlanSwitch(){} function renderEpisode(){rendered='source'}function renderVoiceStart(){rendered='upload'}
        """
        result = preview_js.run(['projectPlanMode', 'directMontage', 'renderPlan'], """
          renderPlan();const ready=[rendered,$('view-plan-label').textContent,$('project-plan').attrs['aria-label']];
          state.plan=null;renderPlan();const empty=rendered;
          state.project.plan_mode='director';renderPlan();
          console.log(JSON.stringify([ready,empty,rendered,$('view-plan-label').textContent]));
        """, prelude)
        self.assertEqual(result, [['source', 'Озвучка', 'Озвучка, сценарій і розпізнаний текст'],
                                  'upload', 'upload', 'План ролика'])

    def test_direct_episode_preserves_script_transcript_without_frame_controls(self):
        prelude = """
          class Node {constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.isConnected=true;this.listeners={};this.classList={toggle(){}};}
            append(...items){this.children.push(...items)}setAttribute(){}addEventListener(event,handler){this.listeners[event]=handler} }
          const document={createElement:tag=>new Node(tag)};
          const state={project:{id:'p',plan_mode:'direct',production:{}},channels:[],
            plan:{script:'Original script',frames:[{number:1}]}};
          const voiceOpen={};let makeCalls=0,tableCalls=0;
          function voicePlayer(){return null}function buildMake(){makeCalls++}
          function episodeFold(name){const n=new Node('details');n.label=name;return n}
          function episodeAnalysis(){return {report:{recognized_text:'Recognized speech'}}}
          function appendSpeechReport(n){n.append(new Node('report'))}
          function planTable(){tableCalls++;return new Node('table')}function madeSet(){return new Set()}
          function flatten(n){return [{className:n.className,label:n.label,text:n.textContent},
              ...n.children.flatMap(flatten)]}
        """
        director = (preview_js.FRONTEND/'director.js').read_text()
        arrange = director[director.index('function arrangeEpisode(episode){'):director.index('// The voice itself')]
        result = preview_js.run(['projectPlanMode', 'directMontage'], """
          const direct=new Node();arrangeEpisode(direct);const directCounts=[makeCalls,tableCalls];
          const before=flatten(direct);function findHeard(n){return n.label==='Розпізнаний текст'?n:n.children.map(findHeard).find(Boolean)}
          const heard=findHeard(direct);heard.open=true;heard.listeners.toggle();
          state.project.plan_mode='director';const planned=new Node();arrangeEpisode(planned);
          console.log(JSON.stringify({nodes:flatten(direct),before,directCounts,plannedCounts:[makeCalls,tableCalls]}));
        """, prelude+'\n'+arrange)
        self.assertEqual(result['directCounts'], [0, 0])
        self.assertEqual(result['plannedCounts'], [1, 1])
        self.assertIn('Original script', [n.get('text') for n in result['nodes']])
        self.assertIn('Recognized speech', [n.get('text') for n in result['nodes']])
        self.assertNotIn('Recognized speech', [n.get('text') for n in result['before']])
        self.assertNotIn('episode-director', [n.get('className') for n in result['nodes']])
        self.assertNotIn('episode-make', [n.get('className') for n in result['nodes']])


if __name__ == '__main__':
    unittest.main()
