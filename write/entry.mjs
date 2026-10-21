export function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

export function entryNumbers(source) {
  const clean = source.replace(/<!--[\s\S]*?-->/g, '');
  return [...clean.matchAll(/<article\b[^>]*\bid="(\d+)"/g)].map(match => Number(match[1]));
}

export function nextNumber(source) {
  const numbers = entryNumbers(source);
  if (!numbers.length) throw new Error('単位が見つかりません。元の index.html を選んでください。');
  if (new Set(numbers).size !== numbers.length) throw new Error('元のページに番号の重複があります。');
  return String(Math.max(...numbers) + 1).padStart(3, '0');
}

export function makeEntry({number, date, title, body, halt = false, time = ''}) {
  if (!/^\d{3,}$/.test(number) || Number(number) < 1) throw new Error('番号を確認してください。');
  const parsedDate = new Date(date + 'T00:00:00Z');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(parsedDate.getTime()) || parsedDate.toISOString().slice(0,10) !== date)
    throw new Error('日付を確認してください。');
  if (halt && !/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) throw new Error('停止を記した時刻を入力してください。');
  if (!halt && (!title.trim() || !body.trim())) throw new Error('題と本文を入力してください。');
  const content = halt ? '    <p class="mark">本日停止</p>' :
    '    <h2>' + escapeHTML(title.trim()) + '</h2>\n' + body.trim().split(/\r?\n\s*\r?\n/).map(block => {
      const lines = block.split(/\r?\n/);
      const quote = lines.every(line => /^>\s?/.test(line));
      const text = quote ? lines.map(line => line.replace(/^>\s?/, '')).join('\n') : block;
      const tag = quote ? 'blockquote' : 'p';
      return `    <${tag}>${escapeHTML(text)}</${tag}>`;
    }).join('\n');
  return `  <article class="entry${halt ? ' halt' : ''}" id="${number}">
    <div class="meta label">
      <span class="no">No. ${number}</span>
      <span>${date.replaceAll('-', '.')}${halt ? ' ' + time : ''}</span>
    </div>
${content}
  </article>`;
}

export function insertEntry(source, entry) {
  const id = entry.match(/^  <article\b[^>]*\bid="(\d+)"/);
  if (!id || id[1] !== nextNumber(source)) throw new Error('番号が最新の原本と一致しません。読み直して生成してください。');
  const main = source.indexOf('<main>');
  const end = source.indexOf('</main>', main);
  if (main < 0 || end < 0) throw new Error('本文の挿入位置が見つかりません。');
  const matches = source.slice(main, end).matchAll(/<!--[\s\S]*?-->|<article\b[^>]*>/g);
  for (const match of matches) {
    if (match[0].startsWith('<article')) {
      const point = main + match.index;
      return source.slice(0, point) + entry.trimStart() + '\n\n  ' + source.slice(point);
    }
  }
  throw new Error('既存の単位が見つかりません。');
}
