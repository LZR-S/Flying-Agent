const $ = id => document.getElementById(id);
const english = {
  'Flight / v1 摄影观测台':'Flight / v1 Photography Console',
  'Flight 观测台首页':'Flight console home',
  '摄影观测台':'Photography Console','连接中':'Connecting','本地在线':'Local Online','连接中断':'Disconnected',
  'Webots 任务控制':'Webots Mission Control','读取状态':'Loading status','正在连接控制服务…':'Connecting to control service…',
  '摄影指令':'Photo brief','描述主体、范围与构图':'Describe the subject, framing, and composition',
  '场景':'Scene','露台':'Terrace','正面':'Facing','开阔':'Open','隐藏':'Hidden','模型接口':'Provider','模型':'Model','预算（秒）':'Time budget (s)',
  '导航图像历史':'Navigation image history','当前图像 + 最近导航帧，支持按需回看':'Current image + recent navigation frames for review',
  '参考图工具':'Reference image tool','允许模型按需生成一次；合成图仅供构图参考':'Allow one on-demand generation; synthetic images are for composition only',
  '启动 Webots · 开始任务':'Start Webots · Start mission','启动 Webots · 工程检查':'Start Webots · System check','停止并降落':'Stop and land',
  '启动后模型可自主起飞。停止请求进入运行层收尾；历史回放不会触发飞行。':'The model may take off after start. A stop request triggers runtime shutdown; replay never controls flight.',
  '当前控制任务：':'Active control run: ','（无活动控制）':' (no active control)','查看当前任务':'View active run',
  '任务概览':'Mission overview','等待摄影任务':'Waiting for a photo mission','待连接':'Waiting for connection','运行记录':'Run history','选择运行记录':'Select run',
  '正在读取记录…':'Loading runs…','尚无运行记录':'No runs yet','下载 Trace':'Download trace','运行状态':'Runtime status','等待开始':'Waiting to start',
  '观察、决策、动作与复核由同一个循环执行':'Observation, decisions, actions, and review run in one loop',
  '无人机视角':'Drone View','画面模式':'View mode','取景器':'Viewfinder','完整 RGB':'Full RGB','成片预览':'Photo preview','决策依据':'Decision evidence',
  '无人机当前视角':'Current drone view','等待图像输入':'Waiting for image input','任务开始后，画面将在这里显示':'The feed will appear here when the mission starts',
  '预览与模型观察分别记录':'Preview and model observations are recorded separately','模型辅助线：':'Model guides: ','关':'Off','九宫格':'Rule of thirds','黄金分割':'Golden ratio',
  '全屏画面':'Fullscreen','上一帧':'Previous frame','播放历史帧':'Play recorded frames','下一帧':'Next frame','历史画面时间轴':'Frame timeline','最新画面':'Live view',
  '遥测状态':'Telemetry','电池':'Battery','飞行状态':'Flight status','图像年龄':'Frame age','飞行链路':'Flight link','未知':'Unknown','无遥测数据':'No telemetry',
  '公共 RGB 与飞行状态':'Public RGB and flight status','决策与行动':'Decisions and Actions','事件类型筛选':'Event filters',
  '显示决策、动作和关键事件，隐藏常规观测':'Show decisions, actions, and key events; hide routine observations',
  '关键':'Key','决策':'Decisions','动作':'Actions','异常':'Errors','包含所有观测记录':'Include all observations','全部':'All',
  '自动滚动到最新事件':'Auto-scroll to latest event','跟随':'Follow','搜索说明、工具或事件…':'Search notes, tools, or events…','搜索事件':'Search events',
  '任务事件时间轴':'Mission event timeline','任务轨迹将在这里展开':'Mission trace will appear here','逐步查看操作说明、动作结果与关键事件':'Review actions, results, and key events step by step',
  '等待数据':'Waiting for data','运行统计与报告':'Run metrics and reports','运行统计':'Run Metrics','独立评测尚未生成':'Independent evaluation is not available yet',
  '候选照片':'Candidate Photos','下载结果':'Download results','等待第一张照片':'Waiting for the first photo','拍摄结果、构图评估与最终选片将在这里呈现':'Photos, composition review, and final selection will appear here',
  '合成构图参考':'Synthetic Composition Reference','非实拍、不可交付':'Synthetic, not deliverable','观察 · 决策 · 行动 · 复核':'Observe · Decide · Act · Review',
  '实时观测 / 历史回放':'Live view / History replay','关闭照片':'Close photo','关闭 (Esc)':'Close (Esc)','候选照片完整画面':'Full candidate photo',
  '待命':'Idle','启动中':'Starting','运行中':'Running','收尾中':'Stopping','已结束':'Finished','启动失败':'Start failed','已完成':'Completed',
  '部分交付':'Partially delivered','已中止':'Aborted','未完成':'Incomplete','无活动':'Inactive','有活动':'Active','满足':'Satisfied','不满足':'Unsatisfied',
  '异常收尾':'Recovery','工作流':'Workflow','飞行动作':'Flight action','拍摄':'Capture','裁剪':'Crop','配置取景框':'Set photo frame',
  '生成构图参考':'Generate reference','照片复核':'Photo review','回看图像':'Review images','选片并结束':'Select photo and finish',
  'Webots 任务占用中':'Webots mission in progress','Webots · 本地模拟器':'Webots · Local simulator','未配置':'Not configured',
  '工程检查（无 API）':'Engineering check (no API)','阿里云官方':'Alibaba Cloud official','自定义环境变量':'Custom environment variables',
  '控制请求必须来自当前本地面板。':'Control requests must come from this local console.',
  '任务参数无效，请检查场景、模型、时长和任务文本。':'Invalid mission settings. Check scene, model, duration, and brief.',
  '本地控制操作失败，请检查 Webots 与运行目录。':'Local control failed. Check Webots and the run directory.',
  '已有 Webots 任务正在运行或收尾。':'A Webots mission is already running or stopping.',
  '未找到 Webots 可执行文件。':'Webots executable not found.',
  '另一个工作台仍持有 Webots 任务，请等待其结束。':'Another console still owns the Webots mission. Wait for it to finish.',
  '启动器未生成结果；请检查本机 .dashboard 运行日志。':'The launcher produced no result. Check the local .dashboard log.',
  '起飞 → 悬停 30 秒 → 降落；不调用模型':'Take off → hover 30 s → land; no model call','无':'None',
  '无标注成片预览':'Unannotated photo preview','实时取景':'Live view','不代表模型已看过此帧':'The model may not have seen this frame',
  '模型决策依据':'Model decision evidence','留档取景器':'Archived viewfinder','原始导航帧':'Original navigation frame','同次曝光':'Same exposure',
  '标注与模型输入一致':'Guides match model input','历史导航帧':'Recorded navigation frame','原始曝光':'Original exposure',
  '此帧没有成片预览':'No photo preview for this frame','设置取景框后会显示对应预览；可切换完整 RGB':'Set a photo frame to show a preview; switch to Full RGB anytime',
  '任务运行或读取记录后显示':'Shown during a mission or after loading a run','无标注画面':'Unannotated image','已落地':'Landed','飞行中':'Airborne','未确认':'Unconfirmed',
  '已连接':'Connected','已断开':'Disconnected','实时公共状态':'Live public status','曝光时记录状态':'Status at exposure','已结束 · 浏览留档':'Finished · Browsing archive',
  '请求':'Request','依据':'Evidence','查看图像':'View image','事件 JSON':'Event JSON','暂无匹配事件':'No matching events','切换筛选条件或等待任务更新':'Change filters or wait for updates',
  '显示匹配事件最近':'Showing latest','条':'matching events','此依据帧不在当前保留的事件窗口中，请下载 Trace 复核。':'This evidence frame is outside the retained event window. Download the trace to review it.',
  '合成参考':'Synthetic reference','非交付照片':'Not a deliverable photo','源图':'Source image','尚未生成参考图；该工具由模型按需调用。':'No reference image yet; the model may request one.',
  '裁剪照片':'Cropped photo','原始照片':'Original photo','最终交付':'Final selection','原图':'Original','尚无候选照片':'No candidate photos yet',
  '失败运行也会保留动作、异常与降落记录':'Failed runs retain actions, errors, and landing records','最终选择：':'Final selection: ','未选择':'None selected',
  '照片复核为模型自评；独立摄影验收：':'Photo review is the model’s own assessment; independent photo evaluation: ','通过':'Passed','未通过':'Failed','待评':'Pending',
  '裁剪交付候选':'Cropped delivery candidate','完整原始照片':'Full original photo','曝光':'Captured','来源':'Source','下载 PNG':'Download PNG','查看原图':'View original',
  '模型自评 · 非独立验收':'Model self-review · Not independent evaluation','后续选择：':'Next step: ','质量问题':'Quality issues','未列出':'None listed','此图片没有复核记录':'No review for this image',
  '参考图对照':'Reference comparison','继续参考':'Keep reference','弃用合成参考':'Discard synthetic reference','曝光与裁剪来源 JSON':'Exposure and crop provenance JSON',
  '动作请求 / 实际执行':'Action requests / Executed','API 尝试 / 累计耗时':'API attempts / Total time','起飞期间仿真时间':'Airborne simulation time',
  '输入 / 输出 token':'Input / output tokens','收尾动作 / 未知结果':'Recovery actions / Unknown results','降落来源 / 已确认':'Landing source / Confirmed',
  '工程脚本':'Engineering script','是':'Yes','否':'No','参考图生成次数 / 耗时':'Reference generations / Time','独立飞行评测':'Independent flight evaluation',
  '空中接触：':'Airborne contact: ','全部接触采样：':'All contact samples: ','（包含地面）':' (including ground)',
  '边界：':'Bounds: ','仿真/墙钟：':'Simulation / wall time: ','输入审计：':'Input audit: ','摄影盲审：':'Blind photo review: ',
  '越界':'Out of bounds','未提供':'Unavailable','独立评测将在运行结束后生成；未提供的数据记为 —。':'Independent evaluation is generated after the run; missing data is shown as —.',
  'HTML 报告':'HTML report','评测 JSON':'Evaluation JSON','动作 CSV':'Actions CSV',
  '正在执行飞行动作':'Executing flight action','正在生成构图参考':'Generating composition reference','正在等待模型 API':'Waiting for model API',
  '飞控与预览持续运行':'Flight control and preview remain active','动作执行':'Executing action','生成参考图':'Generating reference','模型决策':'Model decision',
  '等待照片复核':'Waiting for photo review','准备':'Preparing','未选定照片':'No photo selected','待复核':'Review pending',
  '统一循环 · 按实际工具调用显示状态':'Unified loop · Status reflects actual tool calls','等待启动器创建运行记录…':'Waiting for launcher to create run…',
  '运行记录暂时不可用：':'Run temporarily unavailable: '
};
const translations=Object.entries(english).sort((a,b)=>b[0].length-a[0].length);
const textSources=new WeakMap(),attributeSources=new WeakMap();
let language=localStorage.getItem('flight-language')==='zh-CN'?'zh-CN':'en';
let briefEdited=false;
const translate=value=>language==='en'&&/[\u3400-\u9fff]/.test(value)?translations.reduce((text,[from,to])=>text.replaceAll(from,to),value):value;
function localizePage() {
  document.documentElement.lang=language;
  const button=$('language-toggle');
  const buttonText=language==='en'?'中文':'English';
  const buttonLabel=language==='en'?'Switch to Chinese':'切换到英文';
  if(button.textContent!==buttonText)button.textContent=buttonText;
  if(button.getAttribute('aria-label')!==buttonLabel)button.setAttribute('aria-label',buttonLabel);
  const title='Flight / v1 摄影观测台';document.title=translate(title);
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()) {
    const node=walker.currentNode;
    if(node.parentElement?.closest('textarea, pre, [data-no-localize], #language-toggle'))continue;
    const previous=textSources.get(node);
    const source=previous&&node.nodeValue===previous.rendered?previous.source:node.nodeValue;
    const rendered=translate(source);
    textSources.set(node,{source,rendered});
    if(node.nodeValue!==rendered)node.nodeValue=rendered;
  }
  for(const element of document.querySelectorAll('[title], [aria-label], [alt], [placeholder]')) {
    if(element.closest('[data-no-localize], #language-toggle'))continue;
    let sources=attributeSources.get(element);
    if(!sources){sources=new Map();attributeSources.set(element,sources);}
    for(const name of ['title','aria-label','alt','placeholder']) {
      if(!element.hasAttribute(name))continue;
      const value=element.getAttribute(name),previous=sources.get(name);
      const source=previous&&value===previous.rendered?previous.source:value;
      const rendered=translate(source);
      sources.set(name,{source,rendered});
      if(value!==rendered)element.setAttribute(name,rendered);
    }
  }
}
function setLanguage(next) {
  language=next;localStorage.setItem('flight-language',next);
  const brief=$('control-brief');
  const defaults={en:'Find a person and take a 2:3 vertical half-body photo from head to thighs, keeping hair, hands, and any held object in frame.',
    'zh-CN':'找到人物，拍一张2:3竖幅半身照，从头顶到大腿，保留头发、手和手持物'};
  if(!briefEdited&&Object.values(defaults).includes(brief.value))brief.value=defaults[next];
  state.runsKey=state.providerKey=state.traceKey=state.photosKey='';
  if(state.control)renderControl(state.control);
  if(state.snapshot)render();
  if($('shot-dialog').open)showPhoto($('shot-dialog').dataset.photoId);
  localizePage();
}
$('language-toggle').onclick=()=>setLanguage(language==='en'?'zh-CN':'en');
$('control-brief').addEventListener('input',()=>{briefEdited=true;});
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = seconds => seconds == null ? '—' : `${Math.floor(Math.max(0,seconds)/60).toString().padStart(2,'0')}:${Math.floor(Math.max(0,seconds)%60).toString().padStart(2,'0')}`;
const num = value => value == null ? '—' : Number(value).toLocaleString(language,{maximumFractionDigits:1});
const labels = {idle:'待命',starting:'启动中',running:'运行中',stopping:'收尾中',finished:'已结束',failed:'启动失败',completed:'已完成',partial:'部分交付',aborted:'已中止',incomplete:'未完成',inactive:'无活动',active:'有活动',satisfied:'满足',unsatisfied:'不满足',unknown:'未知',model:'模型',recovery:'异常收尾',workflow:'工作流'};
const toolLabels = {act:'飞行动作',capture:'拍摄',crop_photo:'裁剪',photo_frame:'配置取景框',generate_reference:'生成构图参考',review_photo:'照片复核',view_images:'回看图像',finish:'选片并结束'};
const state = {run:null,cursor:0,events:[],snapshot:null,preview:null,control:null,view:'viewfinder',frameIndex:null,filter:'key',follow:true,playing:null,evidence:null,evidenceContext:null,generation:0,traceKey:'',photosKey:'',providerKey:''};
setLanguage(language);
let localeQueued=false;
new MutationObserver(()=>{
  if(localeQueued)return;
  localeQueued=true;
  queueMicrotask(()=>{localeQueued=false;localizePage();});
}).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','alt','placeholder']});
let busyControl = false;

async function api(path, options) {
  const response = await fetch(path,{cache:'no-store',...options,signal:AbortSignal.timeout(10000)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function notice(message) { $('notice').textContent=message; $('notice').hidden=!message; }
function controlError(message) { $('control-error').textContent=message; $('control-error').hidden=!message; }
function link(id,url) { const a=$(id); a.classList.toggle('disabled',!url); a.setAttribute('aria-disabled',String(!url)); if(url) a.href=url; else a.removeAttribute('href'); }
function activate(selector,value,attribute) { document.querySelectorAll(selector).forEach(b=>{const selected=b.dataset[attribute]===value;b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));}); }
function selectRun(run) {
  if (!run || run===state.run) return;
  state.run=run; state.cursor=0; state.events=[]; state.snapshot=null; state.preview=null; state.frameIndex=null; state.evidence=null; state.generation++;
  state.traceKey=state.photosKey=''; stopPlayback();
  $('run-select').value=run; history.replaceState(null,'',`?run=${encodeURIComponent(run)}`);
  $('timeline').replaceChildren(); $('candidates').replaceChildren(); $('references').replaceChildren(); $('camera-image').hidden=true; $('frame-empty').hidden=false;
  render(); pollSnapshot();
}
async function refreshRuns() {
  const runs=await api('/api/runs'); const select=$('run-select'); const existing=select.value;
  const key=JSON.stringify(runs.map(r=>[r.id,r.status]));
  if(state.runsKey!==key){select.replaceChildren(...runs.map(run=>new Option(`${run.id} · ${labels[run.status]||run.status}`,run.id)));state.runsKey=key;}
  if (!runs.length) select.add(new Option('尚无运行记录',''));
  if (state.run && runs.some(r=>r.id===state.run)) select.value=state.run;
  else if (!state.run && runs.length) {
    const requested=new URLSearchParams(location.search).get('run');
    selectRun(runs.some(r=>r.id===requested)?requested:runs[0].id);
  } else if (existing) select.value=existing;
}
function renderControl(data) {
  state.control=data;
  $('control-state').textContent=labels[data.state]||data.state;
  $('control-state').className=`status-tag ${data.state==='failed'?'error':data.busy?'warn':''}`;
  $('control-message').textContent=data.error || (data.busy?'Webots 任务占用中':'Webots · 本地模拟器');
  $('control-target').textContent=`当前控制任务：${data.active_run||'无'}${data.busy?'':'（无活动控制）'}`;
  $('control-view-run').hidden=!data.active_run;
  $('control-stop').disabled=busyControl||!data.busy||data.state==='stopping';
  const key=JSON.stringify(data.providers);
  if (key!==state.providerKey) {
    const select=$('control-provider'), old=select.value;
    select.replaceChildren(...data.providers.map(p=>{const o=new Option(p.label+(p.ready?'':' · 未配置'),p.id);o.disabled=!p.ready;return o;}));
    if(data.providers.some(p=>p.id===old&&p.ready)) select.value=old;
    else select.value=data.providers.find(p=>p.ready)?.id||'';
    state.providerKey=key; updateProvider(!old);
  }
  for(const id of ['control-brief','control-provider','control-scene','control-model','control-duration','control-history','control-reference']) $(id).disabled=busyControl||data.busy;
  $('control-start').disabled=busyControl||data.busy||!data.webots_available||!data.providers.some(p=>p.id===$('control-provider').value&&p.ready);
}
function updateProvider(resetModel=true) {
  const provider=state.control?.providers.find(p=>p.id===$('control-provider').value);
  if(!provider)return;
  if(resetModel)$('control-model').value=provider.default_model;
  $('provider-endpoint').textContent=provider.endpoint || (provider.id==='scripted'?'起飞 → 悬停 30 秒 → 降落；不调用模型':'未配置');
  $('control-start').textContent=provider.id==='scripted'?'启动 Webots · 工程检查':'启动 Webots · 开始任务';
}
async function control(action,payload={}) {
  if(busyControl)return;
  busyControl=true;controlError('');renderControl(state.control);
  try {
    const data=await api(`/api/control/${action}`,{method:'POST',headers:{'Content-Type':'application/json','X-Drone-Control-Token':state.control.token},body:JSON.stringify(payload)});
    renderControl(data);
    if(action==='start'){await refreshRuns();selectRun(data.active_run);}
  }catch(error){controlError(error.message);}
  finally{busyControl=false; if(state.control)renderControl(state.control);}
}
$('mission-form').addEventListener('submit',event=>{event.preventDefault();control('start',{
  brief:$('control-brief').value,scenario:$('control-scene').value,provider:$('control-provider').value,
  model:$('control-model').value,duration_s:Number($('control-duration').value),navigation_history:$('control-history').checked,reference_generation:$('control-reference').checked});});
$('control-stop').onclick=()=>control('stop');
$('control-view-run').onclick=()=>selectRun(state.control.active_run);
$('control-provider').onchange=()=>updateProvider();
$('run-select').onchange=event=>selectRun(event.target.value);

let snapshotBusy=false;
async function pollSnapshot() {
  if(snapshotBusy||!state.run)return;
  snapshotBusy=true;const run=state.run,generation=state.generation;
  try {
    const snapshot=await api(`/api/snapshot?run=${encodeURIComponent(run)}&after=${state.cursor}`);
    if(generation!==state.generation)return;
    if(snapshot.reset){state.events=[];state.frameIndex=null;state.traceKey='';}
    state.events.push(...snapshot.events); if(state.events.length>10000)state.events.splice(0,state.events.length-10000);
    state.cursor=snapshot.next_cursor;state.snapshot=snapshot;state.preview=snapshot.preview;
    notice('');render();
    if(snapshot.more)setTimeout(pollSnapshot,0);
  }catch(error){if(generation===state.generation)notice(error.message==='not found'?'等待启动器创建运行记录…':`运行记录暂时不可用：${error.message}`);}
  finally{snapshotBusy=false;}
}
async function pollPreview() {
  const run=state.run,generation=state.generation;
  if(!run||state.snapshot?.state.summary)return;
  try{const preview=await api(`/api/preview?run=${encodeURIComponent(run)}`);if(generation===state.generation){state.preview=preview;renderCamera();}}
  catch{/* The main snapshot loop reports connection failures. */}
}
function frames() { return state.events.filter(e=>e.event==='observation'&&e.data.image?.image_url); }
function selectedFrame() {
  const available=frames();
  if(state.frameIndex!==null)return available[Math.min(state.frameIndex,available.length-1)];
  if(state.evidence || state.view==='evidence') {
    const id=state.evidence || state.snapshot?.state.pending_inference?.based_on_frame_id || state.events.findLast(e=>e.event==='decision')?.data.based_on_frame_id;
    return available.findLast(e=>e.data.frame_id===id);
  }
  return available.at(-1);
}
function renderCamera() {
  const snapshot=state.snapshot;
  if(!snapshot)return;
  const available=frames(),frame=selectedFrame(),live=state.preview;
  const useLive=state.frameIndex===null&&!state.evidence&&state.view!=='evidence'&&!snapshot.state.summary&&live;
  let url,identity,caption,observation,time,photo,guides;
  if(useLive) {
    url=state.view==='photo'?live.photo_image_url:state.view==='viewfinder'?(live.viewfinder_image_url||live.image_url):live.image_url;identity=live.frame_id;observation=live.observation;time=live.captured_at;
    guides=live.photo_frame?.guides;
    caption=state.view==='photo'?`无标注成片预览 · 版本 ${live.photo_frame.version}`:'实时取景 · 不代表模型已看过此帧';
  } else if(frame) {
    photo=state.events.findLast(e=>e.event==='frame_preview'&&e.data.source_frame_id===frame.data.frame_id);
    const round=state.snapshot?.state.pending_inference?.round||state.events.findLast(e=>e.event==='decision')?.data.round;
    const context=state.evidence?state.evidenceContext:state.events.findLast(e=>e.event==='context_built'&&e.data.round===round);
    const finder=state.events.findLast(e=>e.event==='viewfinder'&&(state.view==='evidence'&&state.frameIndex===null?e.data.id===context?.data.viewfinder_id&&e.data.source_frame_id===frame.data.frame_id:e.data.source_frame_id===frame.data.frame_id));
    guides=finder?.data.guides;
    url=state.view==='photo'?photo?.data.image_url:['viewfinder','evidence'].includes(state.view)?(finder?.data.image_url||frame.data.image.image_url):frame.data.image.image_url;
    identity=frame.data.frame_id;observation=frame.data;time=frame.data.captured_at;
    caption=state.view==='evidence'&&state.frameIndex===null?(finder?'模型决策依据 · 留档取景器':'模型决策依据 · 原始导航帧'):state.view==='photo'?'无标注成片预览 · 同次曝光':state.view==='viewfinder'&&finder?'留档取景器 · 标注与模型输入一致':'历史导航帧 · 原始曝光';
  }
  const img=$('camera-image');
  if(url){if(img.getAttribute('src')!==url)img.src=url;img.hidden=false;}
  else{img.hidden=true;}
  $('frame-empty').hidden=!!url;
  $('frame-empty-title').textContent=state.view==='photo'?'此帧没有成片预览':'等待图像输入';
  $('frame-empty-detail').textContent=state.view==='photo'?'设置取景框后会显示对应预览；可切换完整 RGB':'任务运行或读取记录后显示';
  $('guide-label').textContent=['raw','photo'].includes(state.view)?'无标注画面':`模型辅助线：${{none:'关',thirds:'九宫格',golden:'黄金分割'}[guides]||'关'}`;
  const fresh=useLive && Date.now()/1000-live.published_at<3;
  $('feed-status').textContent=useLive?(fresh?'LIVE RGB':'STALE PREVIEW'):(state.view==='evidence'&&state.frameIndex===null?'MODEL INPUT':'ARCHIVE');
  $('feed-status').className=`feed-badge ${useLive?(fresh?'live':'stale'):''}`;
  $('frame-sequence').textContent=identity||'FRAME —';$('frame-caption').textContent=caption||'';
  $('battery').textContent=observation?`${num(observation.battery_pct)}%`:'—';
  $('battery-level').style.width=`${observation?.battery_pct||0}%`;
  $('flight-state').textContent=observation?(observation.landed?'已落地':observation.airborne?'飞行中':'未确认'):'—';
  $('frame-age').textContent=observation?`${num(useLive?Math.max(0,Date.now()/1000-time):observation.image_age_s)}s`:'—';
  $('flight-link').textContent=observation?(observation.connected?'已连接':'已断开'):'未知';
  $('telemetry-note').textContent=useLive?'实时公共状态':'曝光时记录状态';
  $('perception-status').textContent=snapshot.state.summary?'已结束 · 浏览留档':'公共 RGB 与飞行状态';
  $('source-age').textContent=time?new Date(time*1000).toLocaleTimeString(language):'SOURCE —';
  $('frame-slider').max=Math.max(0,available.length-1);$('frame-slider').value=state.frameIndex??Math.max(0,available.length-1);
  $('frame-slider').disabled=!available.length;
  $('playback-time').textContent=`${available.length?(state.frameIndex??available.length-1)+1:0} / ${available.length}`;
  for(const id of ['previous-frame','next-frame','play-pause','return-live'])$(id).disabled=!available.length;
}
function stopPlayback(){clearInterval(state.playing);state.playing=null;$('play-pause').textContent='▷';}
function moveFrame(value){state.frameIndex=Math.max(0,Math.min(frames().length-1,value));state.evidence=null;renderCamera();}
$('frame-slider').oninput=e=>{stopPlayback();moveFrame(Number(e.target.value));};
$('previous-frame').onclick=()=>{stopPlayback();moveFrame((state.frameIndex??frames().length-1)-1);};
$('next-frame').onclick=()=>{stopPlayback();moveFrame((state.frameIndex??frames().length-1)+1);};
$('return-live').onclick=()=>{stopPlayback();state.frameIndex=null;state.evidence=null;renderCamera();};
$('play-pause').onclick=()=>{if(state.playing){stopPlayback();return;}state.frameIndex=state.frameIndex??0;$('play-pause').textContent='Ⅱ';state.playing=setInterval(()=>{if(state.frameIndex>=frames().length-1)stopPlayback();else moveFrame(state.frameIndex+1);},700);};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{state.view=b.dataset.view;if(state.view==='evidence')state.frameIndex=null;activate('[data-view]',state.view,'view');renderCamera();});

$('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else $('frame-stage').requestFullscreen().catch(e=>notice(e.message));};

function isError(e){return /error/.test(e.event)||['rejected','unknown'].includes(e.data.status);}
function matches(e){const search=$('event-search').value.toLowerCase();if(search&&!JSON.stringify(e).toLowerCase().includes(search))return false;switch(state.filter){case 'key':return !['observation','maintenance','frame_preview','viewfinder','inference_finished'].includes(e.event);case 'decisions':return ['decision','photo_review'].includes(e.event);case 'actions':return e.event.startsWith('action_')||e.event==='landing';case 'errors':return isError(e);default:return true;}}
function renderTrace(force=false) {
  const key=`${state.cursor}:${state.filter}:${$('event-search').value}`;
  if(!force&&state.traceKey===key)return;state.traceKey=key;
  const timeline=$('timeline'),oldScroll=timeline.scrollTop,opened=new Set([...timeline.querySelectorAll('details[open]')].map(e=>e.dataset.id));
  const events=state.events.filter(matches).slice(-300);
  timeline.innerHTML=events.map(e=>{
    const d=e.data,type=isError(e)?'error':e.event==='decision'?'decision':e.event.startsWith('action_')?'action':e.event==='observation'?'observation':'system';
    const title=e.event==='decision'?(toolLabels[d.tool]||d.tool):d.sdk_command||d.image_id||d.id||d.type||e.event;
    const detail=d.note||d.reason||d.rationale||(['action_started','action_requested'].includes(e.event)?`请求 ${d.action?.kind} ${d.action?.value} ${d.value_unit||''}`:'');
    return `<article class="event-card ${type}"><div class="event-head"><span class="event-kind">${esc(e.event.toUpperCase())}</span><time class="event-time">+${clock(e.elapsed_s)}</time></div><h3 class="event-title">${esc(title)}</h3><p class="event-body" ${d.note||d.reason||d.rationale?'data-no-localize':''}>${esc(detail)}</p><div class="event-footer"><span>${esc(d.status||d.fulfillment||'')}</span><span>${esc(d.source||'')}</span>${d.based_on_frame_id?`<button class="inspect-button" data-frame="${esc(d.based_on_frame_id)}" data-event="${e.id}">依据 ${esc(d.based_on_frame_id)} ↗</button>`:''}${d.image_url?`<a class="inspect-button" href="${esc(d.image_url)}" target="_blank" rel="noopener">查看图像 ↗</a>`:''}</div><details class="raw-details" data-id="${e.id}" ${opened.has(String(e.id))?'open':''}><summary>事件 JSON</summary><pre>${esc(JSON.stringify(d,null,2))}</pre></details></article>`;
  }).join('')||'<div class="timeline-empty"><strong>暂无匹配事件</strong><p>切换筛选条件或等待任务更新</p></div>';
  timeline.querySelectorAll('[data-frame]').forEach(b=>b.onclick=()=>{
    state.evidence=b.dataset.frame;state.evidenceContext=state.events.findLast(e=>e.event==='context_built'&&e.id<Number(b.dataset.event));state.frameIndex=null;state.view='evidence';activate('[data-view]','evidence','view');renderCamera();
    if(!selectedFrame())notice('此依据帧不在当前保留的事件窗口中，请下载 Trace 复核。');
  });
  if(state.follow)timeline.scrollTop=timeline.scrollHeight;else timeline.scrollTop=oldScroll;
  $('event-count').textContent=state.events.length;
  const errors=state.events.filter(isError).length;$('error-count').textContent=errors;$('error-count').hidden=!errors;
  $('trace-detail').textContent=`${state.events.filter(e=>e.event==='decision').length} DECISIONS · ${state.events.filter(e=>e.event==='action_started').length} EXECUTIONS`;
  $('trace-poll').textContent=`显示匹配事件最近 ${events.length} 条`;
}
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{state.filter=b.dataset.filter;activate('[data-filter]',state.filter,'filter');renderTrace(true);});
$('event-search').oninput=()=>renderTrace(true);
$('follow').onclick=()=>{state.follow=!state.follow;$('follow').classList.toggle('active',state.follow);$('follow').setAttribute('aria-pressed',state.follow);if(state.follow)$('timeline').scrollTop=$('timeline').scrollHeight;};
function renderPhotos() {
  const data=state.snapshot.state,photos=data.photos||[],selected=data.summary?.selected_id;
  const key=JSON.stringify([photos,data.references,data.reviews,selected,!!data.summary,data.evaluation?.photo_review]);if(key===state.photosKey)return;state.photosKey=key;
  $('shot-count').textContent=photos.length;
  $('references').innerHTML=(data.references||[]).map(p=>`<a class="shot-card" href="${esc(p.image_url)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(p.image_url)}" alt="合成构图参考 ${esc(p.id)}"><div class="shot-info"><strong>${esc(p.id)} · 合成参考</strong><span>${esc(p.aspect_ratio)} · 非交付照片</span><small>源图 ${esc(p.source_image_id)} · ${num(p.width_px)} × ${num(p.height_px)}</small></div></a>`).join('')||'<div class="candidates-empty"><p>尚未生成参考图；该工具由模型按需调用。</p></div>';

  $('candidates').innerHTML=photos.map(p=>`<button class="shot-card ${p.id===selected?'selected':''}" data-photo="${esc(p.id)}"><img loading="lazy" src="${esc(p.image_url)}" alt="${esc(p.id)} ${p.kind==='crop'?'裁剪照片':'原始照片'}">${p.id===selected?'<span class="selected-label">最终交付</span>':''}<div class="shot-info"><strong>${esc(p.id)}</strong><span>${p.kind==='crop'?'裁剪':'原图'} · ${esc(p.aspect_ratio)}</span><small>${num(p.width_px)} × ${num(p.height_px)} · ${esc(p.source_shot_id||p.source_frame_id)}</small></div></button>`).join('')||'<div class="candidates-empty"><span class="shot-outline"></span><div><strong>尚无候选照片</strong><p>失败运行也会保留动作、异常与降落记录</p></div></div>';
  $('candidates').querySelectorAll('[data-photo]').forEach(b=>b.onclick=()=>showPhoto(b.dataset.photo));
  $('selection-note').hidden=!data.summary;
  $('selection-note').textContent=data.summary?`最终选择：${selected||'未选择'}。照片复核为模型自评；独立摄影验收：${data.evaluation?.photo_review?.compliant===true?'通过':data.evaluation?.photo_review?.compliant===false?'未通过':'待评'}。`:'';
}
function showPhoto(id) {
  const data=state.snapshot.state,photo=data.photos.find(p=>p.id===id);if(!photo)return;
  $('shot-dialog').dataset.photoId=id;
  const review=(data.reviews||[]).findLast(r=>r.image_id===id),source=data.photos.find(p=>p.id===photo.source_shot_id);
  $('shot-title').textContent=`${id}${data.summary?.selected_id===id?' · 最终交付':''}`;$('shot-image').src=photo.image_url;
  $('shot-assessment').innerHTML=`<h3>${photo.kind==='crop'?'裁剪交付候选':'完整原始照片'}</h3><div class="shot-meta">${num(photo.width_px)} × ${num(photo.height_px)} · ${esc(photo.aspect_ratio)}<br>曝光 ${new Date(photo.captured_at*1000).toLocaleString(language)}<br>来源 ${esc(photo.source_shot_id||photo.source_frame_id)}<br>${esc(photo.derivation||'capture')}</div><div class="photo-links"><a href="${esc(photo.image_url)}" download="${esc(id)}.png">下载 PNG ↗</a>${source?`<button id="view-source">查看原图 ↗</button>`:''}</div><h4>模型自评 · 非独立验收</h4>${review?review.checks.map(c=>`<div class="criteria-row ${c.status==='unsatisfied'?'failed':''}"><span data-no-localize>${esc(c.requirement)}</span><span>${esc(labels[c.status]||c.status)}</span></div><p data-no-localize>${esc(c.evidence)}</p>`).join('')+`<h4>后续选择：<span data-no-localize>${esc(review.next_step)}</span></h4><p data-no-localize>${esc(review.rationale)}</p><h4>质量问题</h4><p ${review.quality_issues?.length?'data-no-localize':''}>${esc(review.quality_issues?.join('\n')||'未列出')}</p>`:'<p>此图片没有复核记录</p>'}${review?.reference_comparison?`<h4>参考图对照 · ${esc(review.reference_comparison.reference_id)}</h4><p>${review.reference_comparison.use_reference?'继续参考':'弃用合成参考'} · <span data-no-localize>${esc(review.reference_comparison.reason)}</span></p><p data-no-localize>${esc(review.reference_comparison.differences.join('；'))}</p>`:''}<details class="raw-details"><summary>曝光与裁剪来源 JSON</summary><pre>${esc(JSON.stringify(photo,null,2))}</pre></details>`;
  if(source)$('view-source').onclick=()=>showPhoto(source.id);
  if(!$('shot-dialog').open)$('shot-dialog').showModal();
}
$('close-dialog').onclick=()=>$('shot-dialog').close();
function renderMetrics() {
  const d=state.snapshot.state,e=d.evaluation,s=d.summary,events=state.events;
  const actions=events.filter(row=>row.event==='action_started');const apiEvents=events.filter(row=>row.event==='api_attempt');
  const rows=[['动作请求 / 实际执行',`${s?.action_requests??events.filter(r=>r.event==='action_requested'&&r.data.source!=='recovery').length} / ${e?.counts?.backend_commands??actions.length}`],['API 尝试 / 累计耗时',`${e?.counts?.api_attempts??apiEvents.length} / ${clock(e?.api?.duration_s??apiEvents.reduce((sum,r)=>sum+r.data.duration_s,0))}`],['起飞期间仿真时间',clock(e?.timing?.airborne_simulation_s)],['输入 / 输出 token',`${num(e?.api?.prompt_tokens)} / ${num(e?.api?.completion_tokens)}`],['收尾动作 / 未知结果',`${e?.counts?.recovery_commands??actions.filter(r=>r.data.source==='recovery').length} / ${e?.counts?.unknown??events.filter(r=>r.event==='action_result'&&r.data.status==='unknown').length}`],['降落来源 / 已确认',`${(d.provider?.provider==='scripted'&&s?.landing?.source==='model'?'工程脚本':labels[s?.landing?.source]||s?.landing?.source||'—')} / ${s?(s.landed?'是':'否'):'—'}`]];
  const refs=events.filter(row=>row.event==='reference_attempt');
  rows.push(['参考图生成次数 / 耗时',`${e?.reference_generation?.attempts??refs.length} / ${clock(e?.reference_generation?.duration_s??refs.reduce((sum,r)=>sum+r.data.duration_s,0))}`]);
  $('run-metrics').innerHTML=rows.map(([name,value])=>`<div><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join('');
  $('evaluation-note').textContent=e?`独立飞行评测 · 空中接触：${e.flight?.airborne_contact_free===true?'无':e.flight?.airborne_contact_free===false?'有':'未知'} · 全部接触采样：${num(e.flight?.all_contact_samples)}（包含地面） · 边界：${e.flight?.bounds_ok===true?'通过':e.flight?.bounds_ok===false?'越界':'未知'} · 仿真/墙钟：${e.timing?.sim_wall_ratio?.toFixed(3)??'—'} · 输入审计：${e.model_input_audit||'未提供'} · 摄影盲审：${e.photo_review?.compliant==null?'待评':e.photo_review.compliant?'通过':'未通过'}`:'独立评测将在运行结束后生成；未提供的数据记为 —。';
  const downloads=state.snapshot.downloads;
  $('report-links').innerHTML=[['report.html','HTML 报告'],['evaluation.json','评测 JSON'],['actions.csv','动作 CSV'],['api-metrics.csv','API CSV']].filter(([file])=>downloads[file]).map(([file,label])=>`<a href="${esc(downloads[file])}">${label} ↗</a>`).join('');
}
function render() {
  const snap=state.snapshot;if(!snap)return;
  const d=snap.state,s=d.summary,config=d.configuration;
  $('mission-brief').setAttribute('data-no-localize','');
  $('mission-brief').textContent=config.brief||snap.run.id;
  $('run-status').textContent=labels[snap.run.status]||snap.run.status;
  $('run-status').className=`status-tag ${snap.run.status==='aborted'?'error':''}`;
  $('run-backend').textContent=`Webots · ${config.scenario||'—'}`;
  $('run-model').textContent=`${config.model||'—'}${d.provider?.provider?' / '+d.provider.provider:''}`;
  $('run-updated').textContent=new Date(snap.run.updated_at*1000).toLocaleString(language);
  link('trace-download',snap.downloads['trace.jsonl']);link('summary-download',snap.downloads['summary.json']);
  const pending=d.pending_action||d.pending_reference||d.pending_inference;
  $('pending').hidden=!pending;
  $('pending-title').textContent=d.pending_action?'正在执行飞行动作':d.pending_reference?'正在生成构图参考':'正在等待模型 API';
  $('pending-detail').textContent=d.pending_action?`${d.pending_action.sdk_command||d.pending_action.action?.kind} · ${d.provider?.provider==='scripted'&&d.pending_action.source==='model'?'工程脚本':labels[d.pending_action.source]||d.pending_action.source}`:d.pending_reference?`源图 ${d.pending_reference.source_id} · 飞控与预览持续运行`:`依据 ${d.pending_inference?.based_on_frame_id||'—'} · 飞控与预览持续运行`;
  $('pending-time').textContent=pending?clock(Date.now()/1000-pending.wall_time):'';
  $('current-phase').textContent=s?(labels[s.status]||s.status):d.pending_action?'动作执行':d.pending_reference?'生成参考图':d.pending_inference?'模型决策':d.review_checkpoint?'等待照片复核':toolLabels[d.last_tool]||'准备';
  $('runtime-description').textContent=s?`${s.reason} · ${s.selected_id||'未选定照片'}`:d.review_checkpoint?`待复核 ${d.review_checkpoint.image_id}`:'统一循环 · 按实际工具调用显示状态';
  $('elapsed').textContent=clock(s?.elapsed_s??(d.started_at&&snap.run.status==='active'?Date.now()/1000-d.started_at:d.elapsed_s));
  renderCamera();renderTrace();renderPhotos();renderMetrics();
}
async function pollControlAndRuns() {
  try {const data=await api('/api/control');renderControl(data);await refreshRuns();$('connection').className='connection online';$('connection-text').textContent='本地在线';}
  catch(error){$('connection').className='connection offline';$('connection-text').textContent='连接中断';$('control-start').disabled=$('control-stop').disabled=true;controlError(error.message);}
  finally {setTimeout(pollControlAndRuns,2500);}
}
async function snapshotLoop(){await pollSnapshot();setTimeout(snapshotLoop,1000);}
async function previewLoop(){await pollPreview();setTimeout(previewLoop,300);}
setInterval(()=>{$('wall-clock').textContent=new Date().toLocaleTimeString(language,{hour12:false});if(state.snapshot)render();},1000);
pollControlAndRuns();snapshotLoop();previewLoop();
