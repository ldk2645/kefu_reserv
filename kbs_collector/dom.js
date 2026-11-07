// Fixed read-only DOM code. Page text is data; never evaluated as code.
const mode = arguments[0], selector = arguments[1];
const visible = e => e && e.getClientRects().length > 0 &&
  getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none';
const excluded = 'script,style,noscript,input,textarea,select,button,form,nav,header,footer,[hidden],[aria-hidden="true"],.value-tools,.knowledge-header-info,.knowledge-float-menu,.tagList-container,.content-click-btn,.rule-config-container,.mark-feedback-btn';
function text(e) {
  if (!visible(e) || e.matches(excluded)) return '';
  let out = '';
  for (const n of e.childNodes) {
    if (n.nodeType === Node.TEXT_NODE) out += n.textContent;
    else if (n.nodeType === Node.ELEMENT_NODE) out += n.tagName === 'BR' ? '\n' : text(n);
  }
  return out.replace(/[\t ]+/g,' ').trim();
}
function css(e) {
  if (e.id && document.querySelectorAll('#'+CSS.escape(e.id)).length === 1) return '#'+CSS.escape(e.id);
  const chain = [];
  while (e && e !== document.body) {
    let s = e.tagName.toLowerCase();
    const siblings = e.parentElement ? [...e.parentElement.children].filter(x=>x.tagName===e.tagName) : [];
    if (siblings.length > 1) s += ':nth-of-type('+(siblings.indexOf(e)+1)+')';
    chain.unshift(s); e=e.parentElement;
  }
  return 'body > '+chain.join(' > ');
}
if (mode === 'guard') {
  const body = document.body ? document.body.innerText : '';
  const controls = [...document.querySelectorAll('input[type="password"],iframe[src*="captcha"],[id*="captcha"],[class*="captcha"]')].some(visible);
  return controls || /访问过于频繁|访问受限|无权访问|没有权限|权限不足|拒绝访问|请先登录|请完成验证|安全验证|人机验证|验证码|禁止.{0,12}(?:采集|爬虫)|不允许.{0,12}自动|access denied|too many requests|verify you are human/i.test(body);
}
if (mode === 'inspect') {
  const elements = [...document.querySelectorAll('article,main,[role="main"],section,div')].filter(visible);
  if (elements.length > 3000) return {overflow:true};
  const candidates = elements.filter(e=>visible(e) && !e.closest(excluded) && text(e).length >= 20);
  const roots = candidates.filter(e=>e.matches('article,main,[role="main"],section') || e.id ||
    [...e.children].some(c=>c.matches('h1,h2,h3,p,table,ol,dl'))).slice(0,120);
  return {roots:roots.map(e=>({selector:css(e), tag:e.tagName.toLowerCase(),
    heading:text(e.querySelector('h1,h2,h3')), characters:text(e).length,
    tables:e.querySelectorAll('table').length, links:e.querySelectorAll('a[href]').length})),
    iframe_count:document.querySelectorAll('iframe,frame').length,
    tabs:document.querySelectorAll('[role="tab"]').length,
    lists:document.querySelectorAll('ul,ol,[role="list"]').length};
}
const matches = [...document.querySelectorAll(selector)].filter(visible);
if(matches.length !== 1) return {error:'ROOT_NOT_UNIQUE'};
const root=matches[0];
if (root.matches('html,body') || root.closest(excluded)) return {error:'ROOT_TOO_BROAD'};
if (mode === 'inspect-region') return {selector,tag:root.tagName.toLowerCase(),
  descendants:root.querySelectorAll('*').length,paragraphs:root.querySelectorAll('p').length,
  tables:root.querySelectorAll('table').length,links:root.querySelectorAll('a[href]').length};
const blocks=[];
let observedSection='';
function walk(e, depth=0) {
  if (!visible(e) || e.matches(excluded)) return;
  const tag=e.tagName.toLowerCase();
  // Observed detail editor: read knowledge units only, leaving comments,
  // people, tags and editorial controls outside the selected body.
  if(e.matches('.tree-editor-container')) {
    for(const unit of e.querySelectorAll('.summary-knowledge-item-container')) walk(unit,depth);
    return;
  }
  if(e.matches('.summary-knowledge-item-container')) {
    const title=text(e.querySelector('.knowledge-header__title'));
    blocks.push({kind:'heading',level:2,text:title});
    if(/[?？]|如何|怎么|为什么|是否|能否/.test(title))blocks.push({kind:'question',text:title});
    for(const content of e.querySelectorAll(':scope > .knowledge-paragraph-list'))walk(content,depth);
    return;
  }
  if(e.matches('.paragraph-item')) {
    const label=text(e.querySelector(':scope > .paragraph-title'));
    const start=blocks.length;
    if(label)blocks.push({kind:'label',text:label});
    for(const content of e.querySelectorAll(':scope > .kbs-readonly-rich-text'))walk(content,depth);
    if(/内部/.test(label))for(let i=start;i<blocks.length;i++)blocks[i].audience='internal';
    return;
  }
  if(e.matches('.block.tip')) {
    blocks.push({kind:'note',audience:e.classList.contains('internal')?'internal':'external',text:text(e)});return;
  }
  if (/^h[1-6]$/.test(tag)) {if(Number(tag[1])<=2)observedSection=text(e);blocks.push({kind:'heading',level:Number(tag[1]),text:text(e)});return;}
  // Observed on the authorized product encyclopedia: custom section headers and
  // two-column spec/FAQ lists, without semantic h2/dl markup.
  if(e.matches('.section-header')) {
    observedSection=text(e);blocks.push({kind:'heading',level:2,text:observedSection});return;
  }
  if(e.matches('ul.spec-list')) {
    for(const row of [...e.children].filter(c=>c.tagName==='LI'&&visible(c))) {
      const label=row.querySelector('.spec-label'), fieldValue=row.querySelector('.spec-value');
      if(label && fieldValue && visible(label) && visible(fieldValue)) {
        const key=text(label), value=text(fieldValue);
        if(/FAQ|常见问题|问答|故障排查/i.test(observedSection)||/[?？]$|^(?:问[:：]|如何|怎么|为什么|是否|能否)/.test(key)) {
          blocks.push({kind:'question',text:key});walk(fieldValue,depth);
        } else {
          blocks.push({kind:'field',field_name:key,value,text:key+'：'+value});
        }
        for(const note of row.querySelectorAll('.block.tip')) {
          if(visible(note))blocks.push({kind:'note',audience:note.classList.contains('internal')?'internal':'external',text:text(note)});
        }
        continue;
      }
      const cells=[...row.children].filter(visible);
      if(cells.length!==2) {for(const cell of cells)walk(cell,depth);continue;}
      const key=text(cells[0]), value=text(cells[1]);
      if(/FAQ|常见问题|问答|故障排查/i.test(observedSection)||/[?？]$|^(?:问[:：]|如何|怎么|为什么|是否|能否)/.test(key)) {
        blocks.push({kind:'question',text:key});walk(cells[1],depth);
      } else if(cells[1].querySelector('ol,ul,table')) {
        blocks.push({kind:'heading',level:3,text:key});walk(cells[1],depth);
      } else {
        blocks.push({kind:'field',field_name:key,value,text:key+'：'+value});
      }
    }
    return;
  }
  if (tag==='table') {
    blocks.push({kind:'table',rows:[...e.rows].filter(visible).map(r=>[...r.cells].filter(visible).map(c=>({text:text(c),rowspan:c.rowSpan,colspan:c.colSpan,header:c.tagName==='TH'})))});return;
  }
  if (tag==='ol'||tag==='ul') {
    let index=Number(e.getAttribute('start')||1);
    for(const li of [...e.children].filter(c=>c.tagName==='LI' && visible(c))) {
      if(li.hasAttribute('value')) index=Number(li.getAttribute('value'));
      const direct=[...li.childNodes].filter(n=>!(n.nodeType===1 && ['OL','UL'].includes(n.tagName)))
        .map(n=>n.nodeType===3?n.textContent:text(n)).join(' ').trim();
      blocks.push({kind:'step',number:tag==='ol'?index:null,text:direct,depth}); index++;
      for(const sub of [...li.children].filter(c=>['OL','UL'].includes(c.tagName))) walk(sub,depth+1);
    } return;
  }
  if (tag==='p'||tag==='dt'||tag==='dd'||tag==='summary'||tag==='pre'||tag==='blockquote') {
    blocks.push({kind:tag==='dt'?'question':tag==='dd'?'answer':'paragraph',text:text(e)});return;
  }
  let direct='';
  const flush=()=>{if(direct.trim()) blocks.push({kind:'paragraph',text:direct.trim()});direct='';};
  for(const n of e.childNodes) {
    if(n.nodeType===3) direct+=n.textContent;
    else if(n.nodeType===1) {
      if(['SPAN','A','STRONG','EM','B','I','CODE','SMALL','BR','LABEL'].includes(n.tagName)) direct+=n.tagName==='BR'?'\n':text(n);
      else {flush();walk(n,depth);}
    }
  } flush();
}
walk(root);
function linkAudience(a) {
  if(a.closest('.block.tip.internal'))return 'internal';
  const item=a.closest('.paragraph-item');
  return item && /内部/.test(text(item.querySelector('.paragraph-title')))?'internal':'external';
}
const links=[...root.querySelectorAll('a[href]')].filter(a=>visible(a)&&!a.closest(excluded)).map(a=>({
  title:text(a), url:a.href, raw_href:a.getAttribute('href'),
  audience:linkAudience(a),
  context:text(a.closest('p,li,figure,section') || a).slice(0,1200)}));
return {title:text(root.querySelector('h1,h2')) || document.title,
  page_title:document.title, frame_url:location.href, blocks, links,
  displayed_times:[...root.querySelectorAll('time')].filter(visible).map(e=>text(e)),
  characters:text(root).length};
