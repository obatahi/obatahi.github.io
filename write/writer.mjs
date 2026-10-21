import {nextNumber, makeEntry, insertEntry} from './entry.mjs';

const $ = id => document.getElementById(id);
let source = '', fromFile = false, article = '', updated = '', busy = false;
const localParts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
const part = type => localParts.find(p => p.type === type).value;
$('date').value = `${part('year')}-${part('month')}-${part('day')}`;

function invalidate() {
  $('result').hidden = true;
  article = updated = '';
  $('copy-status').textContent = '';
}
function useSource(text) {
  const number = nextNumber(text);
  source = text;
  $('number').value = number;
  $('generate').disabled = false;
  $('status').textContent = `原本を読み込みました。次は No. ${number} です。`;
}
async function fetchSource() {
  const response = await fetch('https://raw.githubusercontent.com/obatahi/obatahi.github.io/main/index.html', {cache:'no-store', credentials:'omit', referrerPolicy:'no-referrer'});
  if (!response.ok) throw new Error('最新の原本を取得できませんでした。読み直すか、保存した index.html を選択してください。');
  useSource(await response.text());
}
async function reload() {
  if (busy) return;
  busy = true;
  invalidate();
  $('generate').disabled = true;
  $('error').textContent = '';
  try { await fetchSource(); fromFile = false; }
  catch(error) { source = ''; $('status').textContent = '原本を読み込めませんでした。'; $('error').textContent = error.message; }
  finally { busy = false; }
}
$('reload').addEventListener('click', reload);
$('source-file').addEventListener('change', async event => {
  invalidate();
  try { useSource(await event.target.files[0].text()); fromFile = true; $('error').textContent = ''; }
  catch(error) { source = ''; $('generate').disabled = true; $('error').textContent = error.message; }
});
$('form').addEventListener('input', invalidate);
$('halt').addEventListener('change', () => {
  const halt = $('halt').checked;
  $('writing').hidden = halt;
  $('time-label').hidden = !halt;
  $('title').required = $('body').required = !halt;
  $('time').required = halt;
});
$('form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !source) return;
  busy = true;
  $('generate').disabled = true;
  $('error').textContent = '';
  invalidate();
  // Capture the draft before the asynchronous source refresh.
  const draft = {date:$('date').value, title:$('title').value, body:$('body').value, halt:$('halt').checked, time:$('time').value};
  const controls = [...$('form').querySelectorAll('input, textarea, button'), $('reload'), $('source-file')];
  controls.forEach(control => control.disabled = true);
  try {
    if (!fromFile) await fetchSource();
    article = makeEntry({...draft, number:nextNumber(source)});
    updated = insertEntry(source, article);
    // makeEntry escapes all user input; only its fixed article markup is parsed.
    const parsed = new DOMParser().parseFromString(article, 'text/html');
    $('preview').replaceChildren(document.importNode(parsed.querySelector('article'), true));
    $('code').value = article;
    $('result').hidden = false;
    $('result').scrollIntoView({behavior:'smooth',block:'start'});
  } catch(error) { $('error').textContent = error.message; }
  finally { busy = false; controls.forEach(control => control.disabled = false); $('generate').disabled = !source; }
});
$('copy').addEventListener('click', async () => {
  if (!article) return;
  try { await navigator.clipboard.writeText(article); $('copy-status').textContent = 'コピーしました。'; }
  catch { $('code').focus(); $('code').select(); $('copy-status').textContent = 'HTMLを選択しました。コピーしてください。'; }
});
$('download').addEventListener('click', () => {
  if (!updated) return;
  const url = URL.createObjectURL(new Blob([updated], {type:'text/html;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url; link.download = 'index.html'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
reload();
