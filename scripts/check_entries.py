"""index.html の単位（記事）を検査する。標準ライブラリのみ。

検査1  一つの <p> が 250 字以内
検査2  単位の本文（<p> と <blockquote>）の合計が 2500 字以内
検査3  本文に「私」を含まない（2026.09.30 以前の単位は対象外。blockquote 内は警告のみ）
検査4  置かれた単位の不変（--base で与えた版と比べ、既存の単位の番号・日付・題・本文が同じ）
検査5  停止の回に時刻が併記されている（規則06。2026.09.05 の 037 以降）

文字数は、タグを除いて文字参照を実体に戻したあと、空白・改行（全角空白、
ノーブレークスペース、ゼロ幅文字を含む）をすべて除いた Unicode コードポイント数で数える。

終了コード  0: 失敗なし（警告はありうる）  1: 失敗あり  2: 読み取り不能
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PARAGRAPH_MAX = 250
BODY_MAX = 2500
FIRST_PERSON = '私'
# 「2026年9月以前に置かれた単位」は検査3の対象外。9月30日までを対象外とする。
FIRST_PERSON_EXEMPT_UNTIL = date(2026, 9, 30)
# 規則06（停止した日は、停止と記した時刻を併記する）の適用開始。2026年9月5日の 037 から。
HALT_TIME_FROM = date(2026, 9, 5)

CHECK_NAMES = {
    0: '構造',
    1: '段落の長さ',
    2: '本文の合計',
    3: '「私」の使用',
    4: '置かれた単位の不変',
    5: '停止の時刻',
}

_INVISIBLE = '\u200b\u200c\u200d\u2060\ufeff'   # ゼロ幅スペース・ゼロ幅非結合子・ゼロ幅結合子・ワードジョイナー・BOM
_STRIP = re.compile(r'[\s' + _INVISIBLE + r']+')
_DATE = re.compile(r'(\d{4})\.(\d{1,2})\.(\d{1,2})')
_TIME = re.compile(r'(?<!\d)(\d{1,2}):(\d{2})(?!\d)')


def count_chars(text: str) -> int:
    """空白・改行を除いた文字数。タグは呼び出し側で既に除かれている。"""
    return len(_STRIP.sub('', text))


def normalize(text: str) -> str:
    """表示上同じになる空白の揺れを畳む（比較用）。"""
    return re.sub(r'\s+', ' ', text).strip()


def snippet(text: str, limit: int = 24) -> str:
    text = normalize(text)
    return text if len(text) <= limit else text[:limit] + '…'


# ---------------------------------------------------------------- 解析

@dataclass
class Block:
    tag: str                 # 'p' か 'blockquote'
    classes: tuple
    line: int
    in_quote: bool           # blockquote の中にある p
    top_level: bool          # 他の p / blockquote の中ではない
    parts: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return ''.join(self.parts)


@dataclass
class Unit:
    id: str
    line: int
    classes: tuple
    label: str = ''
    date_text: str = ''
    date: date | None = None
    time: str | None = None
    time_problem: str | None = None
    title: str = ''
    blocks: list = field(default_factory=list)
    stray: str = ''

    @property
    def is_halt(self) -> bool:
        return 'halt' in self.classes or any('mark' in b.classes for b in self.blocks)

    @property
    def body_blocks(self) -> list:
        """本文として数える塊。停止の印（p.mark）は含めない。"""
        return [b for b in self.blocks if b.top_level and 'mark' not in b.classes]

    @property
    def paragraphs(self) -> list:
        return [b for b in self.blocks if b.tag == 'p']

    @property
    def body_chars(self) -> int:
        return sum(count_chars(b.text) for b in self.body_blocks)

    @property
    def name(self) -> str:
        return f'単位{self.id}' + (f'『{normalize(self.title)}』' if self.title else '')


class ParseError(Exception):
    pass


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.units: list[Unit] = []
        self.problems: list[tuple[int, str]] = []
        self._unit: Unit | None = None
        self._meta_depth = 0
        self._span: dict | None = None
        self._meta_spans: list[dict] = []
        self._in_h2 = False
        self._stack: list[Block] = []

    # HTMLParser はコメントを handle_comment に回す。コメント内の雛形は単位にならない。
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = tuple((attrs.get('class') or '').split())
        line = self.getpos()[0]
        if tag == 'article' and 'entry' in classes:
            if self._unit is not None:
                self.problems.append((line, '単位が閉じられないまま次の単位が始まっています。'))
                self._finish()
            self._unit = Unit(id=(attrs.get('id') or '').strip(), line=line, classes=classes)
            self._meta_depth = 0
            self._span = None
            self._meta_spans = []
            self._in_h2 = False
            self._stack = []
            return
        if self._unit is None:
            return
        if tag == 'div':
            if self._meta_depth or 'meta' in classes:
                self._meta_depth += 1
        elif tag == 'span' and self._meta_depth:
            self._span = {'no': 'no' in classes, 'parts': []}
            self._meta_spans.append(self._span)
        elif tag == 'h2':
            self._in_h2 = True
        elif tag in ('p', 'blockquote'):
            block = Block(tag=tag, classes=classes, line=line,
                          in_quote=any(b.tag == 'blockquote' for b in self._stack),
                          top_level=not self._stack)
            self._unit.blocks.append(block)
            self._stack.append(block)
        elif tag == 'br':
            self._data('\n')

    def handle_endtag(self, tag):
        if self._unit is None:
            return
        if tag == 'article':
            self._finish()
        elif tag == 'div' and self._meta_depth:
            self._meta_depth -= 1
        elif tag == 'span' and self._span is not None:
            self._span = None
        elif tag == 'h2':
            self._in_h2 = False
        elif tag in ('p', 'blockquote'):
            for i in range(len(self._stack) - 1, -1, -1):
                if self._stack[i].tag == tag:
                    del self._stack[i:]
                    break

    def handle_data(self, data):
        if self._unit is not None:
            self._data(data)

    def _data(self, data):
        if self._span is not None:
            self._span['parts'].append(data)
        elif self._meta_depth:
            self._meta_spans.append({'no': False, 'parts': [data]})
        elif self._in_h2:
            self._unit.title += data
        elif self._stack:
            for block in self._stack:
                block.parts.append(data)
        elif data.strip():
            self._unit.stray += data

    def _finish(self):
        unit = self._unit
        self._unit = None
        no_text = ' '.join(''.join(s['parts']) for s in self._meta_spans if s['no'])
        unit.label = normalize(re.sub(r'^\s*No\.?\s*', '', no_text))
        rest = normalize(' '.join(''.join(s['parts']) for s in self._meta_spans if not s['no']))
        unit.title = normalize(unit.title)
        m = _DATE.search(rest)
        if m:
            unit.date_text = f'{int(m[1]):04d}.{int(m[2]):02d}.{int(m[3]):02d}'
            try:
                unit.date = date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                unit.date = None
            rest = rest[:m.start()] + ' ' + rest[m.end():]
        t = _TIME.search(rest)
        if t:
            hour, minute = int(t[1]), int(t[2])
            if hour > 23 or minute > 59:
                unit.time_problem = f'{t[0]} は時刻として読めません'
            else:
                unit.time = f'{hour:02d}:{minute:02d}'
        self.units.append(unit)


def parse_units(html: str) -> tuple[list[Unit], list[tuple[int, str]]]:
    collector = _Collector()
    collector.feed(html)
    collector.close()
    if collector._unit is not None:
        collector.problems.append((collector._unit.line, '単位が </article> で閉じられていません。'))
        collector._finish()
    return collector.units, collector.problems


# ---------------------------------------------------------------- 検査結果

@dataclass
class Finding:
    level: str               # 'error' か 'warning'
    check: int
    unit: str                # 単位の表示名。単位をまたぐ問題は空
    message: str
    line: int | None = None

    def render(self) -> str:
        mark = '失敗' if self.level == 'error' else '警告'
        where = f'{self.unit} ' if self.unit else ''
        at = f'（index.html:{self.line}）' if self.line else ''
        return f'[{mark}] {where}検査{self.check}「{CHECK_NAMES[self.check]}」: {self.message}{at}'


def _label(unit: Unit) -> str:
    return unit.name + (f'（{unit.date_text}）' if unit.date_text else '')


def check_structure(units, problems) -> list[Finding]:
    out = [Finding('error', 0, '', msg, line) for line, msg in problems]
    if not units:
        out.append(Finding('error', 0, '', '単位（<article class="entry">）が一つも見つかりません。'))
    seen: dict[str, Unit] = {}
    for unit in units:
        if not unit.id:
            out.append(Finding('error', 0, _label(unit), '単位に id（番号）がありません。', unit.line))
        elif unit.id in seen:
            out.append(Finding('error', 0, _label(unit), f'番号{unit.id}が重複しています。', unit.line))
        seen.setdefault(unit.id, unit)
        if unit.date is None:
            out.append(Finding('error', 0, _label(unit),
                               f'日付を読み取れません（「{unit.date_text or "なし"}」）。YYYY.MM.DD の形で書いてください。', unit.line))
        if unit.stray:
            out.append(Finding('warning', 0, _label(unit),
                               f'p・blockquote・題の外に文字があります（数えられません）: 「{snippet(unit.stray)}」', unit.line))
    return out


def check_paragraphs(unit: Unit) -> list[Finding]:
    out = []
    for i, block in enumerate(unit.paragraphs, 1):
        n = count_chars(block.text)
        if n > PARAGRAPH_MAX:
            out.append(Finding('error', 1, _label(unit),
                               f'{i}つ目のpが{n}字です（上限{PARAGRAPH_MAX}字、{n - PARAGRAPH_MAX}字超過）。'
                               f'冒頭「{snippet(block.text)}」', block.line))
    return out


def check_body_total(unit: Unit) -> list[Finding]:
    total = unit.body_chars
    if total > BODY_MAX:
        return [Finding('error', 2, _label(unit),
                        f'本文の合計が{total}字です（上限{BODY_MAX}字、{total - BODY_MAX}字超過）。', unit.line)]
    return []


def check_first_person(unit: Unit) -> list[Finding]:
    if unit.date is None or unit.date <= FIRST_PERSON_EXEMPT_UNTIL:
        return []
    out = []
    for block in unit.body_blocks:
        n = block.text.count(FIRST_PERSON)
        if not n:
            continue
        i = block.text.index(FIRST_PERSON)
        around = normalize(block.text[max(0, i - 10):i + 11])
        if block.tag == 'blockquote':
            out.append(Finding('warning', 3, _label(unit),
                               f'引用（blockquote）の中に「{FIRST_PERSON}」が{n}回あります。引用なので警告のみです。'
                               f'「…{around}…」', block.line))
        else:
            out.append(Finding('error', 3, _label(unit),
                               f'本文に「{FIRST_PERSON}」が{n}回あります。「…{around}…」', block.line))
    return out


def check_halt_time(unit: Unit) -> list[Finding]:
    if not unit.is_halt or unit.date is None or unit.date < HALT_TIME_FROM:
        return []
    if unit.time_problem:
        return [Finding('error', 5, _label(unit),
                        f'停止の回の時刻が不正です（{unit.time_problem}）。00:00〜23:59 の形で記してください。', unit.line)]
    if unit.time is None:
        return [Finding('error', 5, _label(unit),
                        '停止の回に、停止と記した時刻が併記されていません（規則06）。', unit.line)]
    return []


def _fields(unit: Unit) -> dict:
    return {
        '番号': unit.label,
        '日付': unit.date_text,
        '時刻': unit.time or '',
        '種別': '停止' if unit.is_halt else '通常',
        '題': unit.title,
        '本文': [(b.tag, normalize(b.text)) for b in unit.blocks if b.top_level],
    }


def check_immutable(old_units, new_units) -> list[Finding]:
    new_by_id = {}
    for unit in new_units:
        new_by_id.setdefault(unit.id, unit)
    out = []
    seen = set()
    for old in old_units:
        if old.id in seen:
            continue
        seen.add(old.id)
        new = new_by_id.get(old.id)
        if new is None:
            out.append(Finding('error', 4, _label(old),
                               '置かれた単位が見つかりません。削除、または番号の変更です。'))
            continue
        a, b = _fields(old), _fields(new)
        for key in ('番号', '日付', '時刻', '種別', '題'):
            if a[key] != b[key]:
                out.append(Finding('error', 4, _label(new),
                                   f'{key}が変更されています（「{a[key] or "なし"}」→「{b[key] or "なし"}」）。', new.line))
        if a['本文'] != b['本文']:
            out.append(Finding('error', 4, _label(new), _describe_body_change(a['本文'], b['本文']), new.line))
    return out


def _describe_body_change(old, new) -> str:
    if len(old) != len(new):
        return (f'本文の塊（p・blockquote）の数が変更されています（{len(old)}個→{len(new)}個、'
                f'合計{sum(count_chars(t) for _, t in old)}字→{sum(count_chars(t) for _, t in new)}字）。')
    notes = []
    for i, ((ot, otext), (nt, ntext)) in enumerate(zip(old, new), 1):
        if (ot, otext) != (nt, ntext):
            kind = f'{ot}→{nt}、' if ot != nt else ''
            notes.append(f'{i}つ目の{ot}（{kind}{count_chars(otext)}字→{count_chars(ntext)}字）'
                         f'「{snippet(otext, 16)}」→「{snippet(ntext, 16)}」')
    return '本文が変更されています: ' + ' / '.join(notes)


def run_checks(units, problems, base_units=None) -> list[Finding]:
    findings = check_structure(units, problems)
    for unit in units:
        findings += check_paragraphs(unit)
        findings += check_body_total(unit)
        findings += check_first_person(unit)
        findings += check_halt_time(unit)
    if base_units is not None:
        findings += check_immutable(base_units, units)
    return findings


# ---------------------------------------------------------------- git / 入出力

def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                              encoding='utf-8', check=False)
    except FileNotFoundError:
        return None
    return done.stdout if done.returncode == 0 else None


def resolve_base(root: Path, rev: str | None) -> tuple[str | None, str]:
    """比較対象のコミットを決める。(コミット, 説明)。決められなければ (None, 理由)。"""
    if rev and set(rev) != {'0'}:
        sha = (_git(root, 'rev-parse', '--verify', '--quiet', rev + '^{commit}') or '').strip()
        if sha:
            return sha, f'指定された比較対象 {sha[:10]}'
    reason = '比較対象が指定されていない' if not rev or set(rev) == {'0'} else f'比較対象 {rev[:10]} がこの clone にない'
    for ref in ('origin/main', 'main'):
        sha = (_git(root, 'merge-base', 'HEAD', ref) or '').strip()
        head = (_git(root, 'rev-parse', 'HEAD') or '').strip()
        if sha and sha != head:
            return sha, f'{reason}ため、{ref} との分岐点 {sha[:10]} を使用'
    sha = (_git(root, 'rev-parse', '--verify', '--quiet', 'HEAD~1^{commit}') or '').strip()
    if sha:
        return sha, f'{reason}ため、直前のコミット {sha[:10]} を使用'
    return None, reason + '、直前のコミットも見つからない'


def _escape(value: str, prop: bool = False) -> str:
    value = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    return value.replace(':', '%3A').replace(',', '%2C') if prop else value


def emit(findings: list[Finding], file_label: str = 'index.html') -> None:
    on_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
    for f in findings:
        print(f.render())
        if on_actions:
            props = f'file={_escape(file_label, True)}'
            if f.line:
                props += f',line={f.line}'
            title = f'{f.unit or "単位の検査"} 検査{f.check} {CHECK_NAMES[f.check]}'
            props += ',title=' + _escape(title, True)
            print(f'::{"error" if f.level == "error" else "warning"} {props}::{_escape(f.message)}')


def write_summary(findings, unit_count, notes) -> None:
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if not path:
        return
    errors = [f for f in findings if f.level == 'error']
    lines = ['## 単位の検査', '', f'検査した単位: {unit_count}　失敗: {len(errors)}　警告: {len(findings) - len(errors)}', '']
    lines += [f'- {n}' for n in notes]
    if findings:
        lines += ['', '| 結果 | 単位 | 検査 | 内容 |', '|---|---|---|---|']
        for f in findings:
            result = '失敗' if f.level == 'error' else '警告'
            message = f.message.replace('|', '\\|')
            lines.append(f'| {result} | {f.unit} | {f.check} {CHECK_NAMES[f.check]} | {message} |')
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='index.html の単位を検査する')
    ap.add_argument('--file', default=str(ROOT / 'index.html'), help='検査する HTML（既定: index.html）')
    ap.add_argument('--base', help='検査4の比較対象のコミット。空や 000… のときは分岐点か直前のコミットで代用')
    ap.add_argument('--no-base', action='store_true', help='検査4を行わない')
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    path = Path(args.file)
    try:
        units, problems = parse_units(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError) as e:
        print(f'[失敗] {path} を読めません: {e}')
        return 2

    notes = []
    base_units = None
    if args.no_base:
        notes.append('検査4: --no-base のためスキップ')
    else:
        root = path.resolve().parent
        sha, why = resolve_base(root, args.base)
        if sha is None:
            notes.append(f'検査4: スキップ（{why}）')
        else:
            rel = _git(root, 'rev-parse', '--show-prefix')
            rel = (rel or '').strip() + path.name
            old = _git(root, 'show', f'{sha}:{rel}')
            if old is None:
                notes.append(f'検査4: スキップ（{why}。その版に {rel} がない）')
            else:
                base_units, _ = parse_units(old)
                notes.append(f'検査4: {why}の {rel}（{len(base_units)}単位）と比較')

    findings = run_checks(units, problems, base_units)
    exempt = [u.id for u in units if u.date and u.date <= FIRST_PERSON_EXEMPT_UNTIL
              and any(FIRST_PERSON in b.text for b in u.body_blocks)]
    if exempt:
        notes.append(f'検査3: {FIRST_PERSON_EXEMPT_UNTIL:%Y.%m.%d}以前の単位は対象外'
                     f'（「{FIRST_PERSON}」を含む対象外の単位: {", ".join(exempt)}）')

    print(f'検査した単位: {len(units)}')
    for n in notes:
        print('  ' + n)
    errors = [f for f in findings if f.level == 'error']
    emit(findings)
    write_summary(findings, len(units), notes)
    if errors:
        print(f'\n失敗 {len(errors)}件 / 警告 {len(findings) - len(errors)}件')
        return 1
    print(f'\n失敗なし（警告 {len(findings)}件）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
