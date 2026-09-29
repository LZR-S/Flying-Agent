const {test} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require('puppeteer');

const assets = path.resolve(__dirname, '../src/drone_agent/dashboard');
const run = {id:'demo',status:'active',updated_at:1000};
const photo = {id:'shot_000001',kind:'capture',image_url:'/missing.png',width_px:1200,height_px:1800,aspect_ratio:'2:3',captured_at:1000,source_frame_id:'frame_000001'};
const snapshot = {run,events:[{id:1,event:'decision',elapsed_s:1,data:{tool:'capture',note:'模型正在寻找主体'}}],
  next_cursor:1,more:false,reset:false,preview:null,downloads:{},state:{configuration:{brief:'请拍摄模型雕塑',scenario:'terrace',model:'demo-model'},
    summary:null,photos:[photo],references:[],reviews:[],evaluation:null,provider:null,pending_action:null,pending_reference:null,
    pending_inference:null,review_checkpoint:null,last_tool:'capture',started_at:1000,elapsed_s:1}};

test('dashboard defaults to English and preserves form input across language changes', async () => {
  const server = http.createServer((request, response) => {
    if (request.url === '/api/control') {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({state:'idle',busy:false,active_run:null,providers:[{id:'scripted',label:'工程检查（无 API）',default_model:'scripted',ready:true,endpoint:null}],webots_available:false}));
      return;
    }
    if (request.url === '/api/runs') {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify([run]));
      return;
    }
    if (request.url.startsWith('/api/snapshot')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify(snapshot));
      return;
    }
    if (request.url.startsWith('/api/preview')) {
      response.setHeader('Content-Type', 'application/json');
      response.end('null');
      return;
    }
    const pathname = new URL(request.url, 'http://localhost').pathname;
    const name = pathname === '/' ? 'index.html' : pathname.replace('/assets/', '');
    if (!['index.html', 'dashboard.js', 'dashboard.css'].includes(name)) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html');
    response.end(fs.readFileSync(path.join(assets, name)));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await puppeteer.launch({headless:true});
  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForSelector('#language-toggle');
    await page.waitForFunction(() => document.querySelector('#mission-brief')?.textContent === '请拍摄模型雕塑');
    assert.equal(await page.$eval('html', element => element.lang), 'en');
    assert.match(await page.$eval('#control-heading', element => element.textContent), /Mission Control/);
    assert.match(await page.$eval('#connection-text', element => element.textContent), /Local Online/);
    assert.equal(await page.$eval('.event-body', element => element.textContent), '模型正在寻找主体');
    assert.equal(await page.evaluate(() => document.body.innerText.replace('中文', '').replace('请拍摄模型雕塑', '').replace('模型正在寻找主体', '').match(/[\u3400-\u9fff]/g)), null);
    await page.click('[data-photo="shot_000001"]');
    assert.match(await page.$eval('#shot-assessment', element => element.innerText), /Full original photo/);
    await page.click('#close-dialog');
    await page.$eval('#control-brief', element => {element.value = 'Find the red kite';});
    await page.click('#language-toggle');
    assert.equal(await page.$eval('html', element => element.lang), 'zh-CN');
    assert.match(await page.$eval('#control-heading', element => element.textContent), /任务控制/);
    assert.equal(await page.$eval('#run-status', element => element.textContent), '有活动');
    assert.equal(await page.$eval('#control-brief', element => element.value), 'Find the red kite');
    await page.reload();
    await page.waitForFunction(() => document.documentElement.lang === 'zh-CN');
    assert.equal(await page.$eval('html', element => element.lang), 'zh-CN');
    await page.click('#language-toggle');
    assert.equal(await page.$eval('html', element => element.lang), 'en');
    assert.equal(await page.$eval('#run-status', element => element.textContent), 'Active');
    await page.setViewport({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.evaluate(() => document.querySelector('.brand').getBoundingClientRect().right <= document.querySelector('.topbar-right').getBoundingClientRect().left), true);
    const editedBrief = 'Find a person and take a 2:3 vertical half-body photo from head to thighs, keeping hair, hands, and any held object in frame.';
    await page.$eval('#control-brief', (element, value) => {element.value=value;element.dispatchEvent(new Event('input', {bubbles:true}));}, editedBrief);
    await page.click('#language-toggle');
    assert.equal(await page.$eval('#control-brief', element => element.value), editedBrief);
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
});
