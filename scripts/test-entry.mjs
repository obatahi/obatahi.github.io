import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {nextNumber, makeEntry, insertEntry, entryNumbers} from '../write/entry.mjs';

const source = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const number = nextNumber(source);
const entry = makeEntry({number, date:'2026-10-22', title:'A & B < C',
  body:'一段落目。\n続く行。\n\n> 引用 & 言葉\n> 二行目\n\n<script>alert("x")</script>'});
assert.ok(entry.includes('<h2>A &amp; B &lt; C</h2>'));
assert.ok(entry.includes('<blockquote>引用 &amp; 言葉\n二行目</blockquote>'));
assert.ok(entry.includes('&lt;script&gt;'));
assert.ok(!entry.includes('<script>'));
assert.equal((entry.match(/<p>/g) || []).length, 2);
const updated = insertEntry(source, entry);
assert.equal(updated.replace(entry.trimStart() + '\n\n  ', ''), source);
assert.equal(entryNumbers(updated).length, entryNumbers(source).length + 1);
assert.equal(nextNumber(updated), String(Number(number) + 1).padStart(3, '0'));
assert.throws(() => insertEntry(updated, entry), /番号/);
assert.equal(nextNumber('<!-- <article id="999"> -->' + source), number);
assert.throws(() => nextNumber(source + '<article id="001">'), /重複/);
assert.throws(() => makeEntry({number, date:'2026-02-30', title:'題', body:'本文'}), /日付/);
assert.throws(() => makeEntry({number:'0" onclick="x',date:'2026-10-22',title:'題',body:'本文'}), /番号/);
assert.throws(() => makeEntry({number,date:'2026-10-22',title:'',body:'本文'}), /題と本文/);
assert.throws(() => makeEntry({number,date:'2026-10-22',halt:true,time:'24:00'}), /時刻/);
const halt = makeEntry({number,date:'2026-10-22',halt:true,time:'23:59'});
assert.ok(halt.includes('2026.10.22 23:59'));
assert.ok(halt.includes('<p class="mark">本日停止</p>'));
assert.ok(!halt.includes('<h2>'));
console.log('Passed writer tests: escaping, quotes, source preservation, duplicate prevention, dates and stops.');
