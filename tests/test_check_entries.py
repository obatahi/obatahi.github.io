"""scripts/check_entries.py のテスト。

実際の index.html の単位を取り出し、日付・本文・時刻を加工して検査に通す。
使う単位（017, 023, 029, 037, 038, 083, 093 ほか）は置かれた単位なので、
規則02と検査4により変わらない。
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_entries as ce  # noqa: E402

SOURCE = (ROOT / 'index.html').read_text(encoding='utf-8')


def real(number: str) -> str:
    """index.html から単位の生の HTML を取り出す（検査側の解析器とは別の方法）。"""
    clean = re.sub(r'<!--.*?-->', '', SOURCE, flags=re.S)
    for article in re.findall(r'<article\b[^>]*>.*?</article>', clean, flags=re.S):
        if re.search(rf'<article\b[^>]*\bid="{number}"', article):
            return article
    raise KeyError(number)


def page(*articles: str) -> str:
    return ('<!DOCTYPE html><html><head><title>t</title><style>.entry{}</style></head><body>'
            '<main>\n' + '\n\n'.join(articles) + '\n</main><footer>奥付</footer></body></html>')


def findings(html: str, base: str | None = None):
    units, problems = ce.parse_units(html)
    base_units = ce.parse_units(base)[0] if base is not None else None
    return ce.run_checks(units, problems, base_units)


def errors(html, base=None, check=None):
    return [f for f in findings(html, base) if f.level == 'error' and check in (None, f.check)]


def warnings(html, check=None):
    return [f for f in findings(html) if f.level == 'warning' and check in (None, f.check)]


def redate(article: str, new_date: str) -> str:
    return re.sub(r'<span>\d{4}\.\d{2}\.\d{2}</span>', f'<span>{new_date}</span>', article, count=1)


def para(n: int) -> str:
    return '<p>' + '字' * n + '</p>'


class Parsing(unittest.TestCase):
    def setUp(self):
        self.units, self.problems = ce.parse_units(SOURCE)

    def test_all_units_found_and_commented_templates_ignored(self):
        self.assertEqual(self.problems, [])
        self.assertEqual([u.id for u in self.units], [f'{n:03d}' for n in range(93, 0, -1)])

    def test_unit_fields(self):
        u = {x.id: x for x in self.units}
        self.assertEqual((u['093'].label, u['093'].date_text, u['093'].title), ('093', '2026.10.31', '北'))
        self.assertEqual(len(u['093'].paragraphs), 6)
        # 番号がリンクで包まれている単位でも番号が読める
        self.assertIn('href="/083/"', real('083'))
        self.assertEqual(u['083'].label, '083')
        self.assertEqual(u['083'].title, '榎本&榎本')   # &amp; は実体に戻る
        self.assertEqual(u['017'].blocks[0].tag, 'p')
        self.assertTrue(any(b.tag == 'blockquote' for b in u['017'].blocks))

    def test_halts(self):
        halts = [u.id for u in self.units if u.is_halt]
        self.assertEqual(sorted(halts), ['008', '009', '013', '014', '015', '022', '025', '026',
                                         '027', '029', '030', '031', '032', '037', '038'])
        u = {x.id: x for x in self.units}
        self.assertEqual((u['037'].date_text, u['037'].time), ('2026.09.05', '23:55'))
        self.assertEqual((u['038'].date_text, u['038'].time), ('2026.09.06', '23:24'))
        self.assertIsNone(u['029'].time)
        self.assertEqual(u['037'].body_chars, 0)   # 停止の印は本文に数えない

    def test_time_in_same_span_as_date_is_read(self):
        # write/entry.mjs が書き出す形: <span>2026.10.22 23:59</span>
        html = real('037').replace('<span>2026.09.05</span>\n      <span>23:55</span>',
                                   '<span>2026.09.05 23:55</span>')
        self.assertNotEqual(html, real('037'))
        unit = ce.parse_units(page(html))[0][0]
        self.assertEqual((unit.date_text, unit.time), ('2026.09.05', '23:55'))

    def test_unclosed_and_duplicate_and_empty_are_errors(self):
        self.assertTrue(errors('<main></main>', check=0))
        self.assertTrue(errors(page(real('093'), real('093')), check=0))
        self.assertTrue(errors(page(real('093').replace('2026.10.31', '10月31日')), check=0))
        self.assertTrue(errors(page(real('093').replace('</article>', '')), check=0))


class CountChars(unittest.TestCase):
    def test_tags_whitespace_newlines_are_not_counted(self):
        self.assertEqual(ce.count_chars('あ い\nう\u3000え\u00a0お\t\u200bか'), 6)
        unit = ce.parse_units(page('<article class="entry" id="001"><div class="meta label">'
                                   '<span class="no">No. 001</span><span>2026.11.01</span></div><h2>題</h2>'
                                   '<p>あ<em>い</em> う<br>え\n\n  お&amp;か</p></article>'))[0][0]
        self.assertEqual(unit.body_chars, 7)   # あいうえお&か。&amp; は1字

    def test_real_unit_counts(self):
        u = {x.id: x for x in ce.parse_units(SOURCE)[0]}
        first = u['093'].paragraphs[0].text
        self.assertEqual(ce.count_chars(first), len(re.sub(r'\s', '', first)))
        self.assertEqual(ce.count_chars(first), 34)
        self.assertEqual(u['093'].body_chars, sum(ce.count_chars(b.text) for b in u['093'].paragraphs))

    def test_title_and_meta_are_not_body(self):
        unit = {x.id: x for x in ce.parse_units(SOURCE)[0]}['093']
        self.assertNotIn('北', ''.join(b.text for b in unit.body_blocks).replace('北には、関所がない。', ''))


class Check1Paragraph(unittest.TestCase):
    def test_exactly_250_passes_251_fails(self):
        base = real('093')
        ok = page(base.replace('</article>', '  ' + para(250) + '\n</article>'))
        self.assertEqual(errors(ok, check=1), [])
        ng = page(base.replace('</article>', '  ' + para(251) + '\n</article>'))
        (f,) = errors(ng, check=1)
        self.assertIn('単位093『北』', f.render())
        self.assertIn('7つ目のpが251字', f.message)
        self.assertIn('1字超過', f.message)

    def test_tags_and_whitespace_do_not_push_over_the_limit(self):
        padded = '<p>' + ' <em>字</em>\n' * 250 + '</p>'
        self.assertEqual(errors(page(real('093').replace('</article>', padded + '</article>')), check=1), [])

    def test_blockquote_is_not_a_p(self):
        html = page(real('093').replace('</article>', '<blockquote>' + '字' * 300 + '</blockquote></article>'))
        self.assertEqual(errors(html, check=1), [])


class Check2Total(unittest.TestCase):
    def total_page(self, extra: int):
        # 093 の本文に p（250字×n）を足して、合計を 2500 + extra にする
        unit = {x.id: x for x in ce.parse_units(SOURCE)[0]}['093']
        need = ce.BODY_MAX + extra - unit.body_chars
        paras = [250] * (need // 250) + ([need % 250] if need % 250 else [])
        return page(real('093').replace('</article>', ''.join(para(n) for n in paras) + '</article>'))

    def test_exactly_2500_passes_2501_fails(self):
        self.assertEqual(errors(self.total_page(0), check=2), [])
        (f,) = errors(self.total_page(1), check=2)
        self.assertIn('本文の合計が2501字', f.message)
        self.assertIn('1字超過', f.message)

    def test_blockquote_counts_toward_total_and_halt_mark_does_not(self):
        self.assertEqual(errors(page(real('037')), check=2), [])
        html = page(real('093').replace('</article>', '<blockquote>' + '字' * 2480 + '</blockquote></article>'))
        self.assertTrue(errors(html, check=2))


class Check3FirstPerson(unittest.TestCase):
    def test_real_units_before_cutoff_are_exempt(self):
        # 023 は p に「私」が2つ、017 は blockquote に「私」がある。どちらも8月。
        self.assertIn('私', real('023'))
        self.assertEqual(findings(page(real('023'))), [])
        self.assertEqual(findings(page(real('017'))), [])

    def test_p_after_cutoff_fails(self):
        out = errors(page(redate(real('023'), '2026.11.01')), check=3)
        self.assertEqual(len(out), 2)
        self.assertIn('単位023', out[0].render())
        self.assertIn('「私」が1回', out[0].message)

    def test_blockquote_after_cutoff_is_only_a_warning(self):
        html = page(redate(real('017'), '2026.11.01'))
        self.assertEqual(errors(html, check=3), [])
        (w,) = warnings(html, check=3)
        self.assertIn('blockquote', w.message)

    def test_p_inside_blockquote_is_a_warning(self):
        html = page(redate(real('093'), '2026.11.01').replace(
            '</article>', '<blockquote><p>私は見た。</p></blockquote></article>'))
        self.assertEqual(errors(html, check=3), [])
        self.assertEqual(len(warnings(html, check=3)), 1)

    def test_boundary_dates(self):
        mutated = real('093').replace('<p>北には、関所がない。</p>', '<p>私は北にいる。</p>')
        self.assertNotEqual(mutated, real('093'))
        self.assertEqual(errors(page(redate(mutated, '2026.09.30')), check=3), [])
        self.assertTrue(errors(page(redate(mutated, '2026.10.01')), check=3))

    def test_title_is_not_checked_and_other_wa_characters_are_not_matched(self):
        html = redate(real('093'), '2026.11.01').replace('<h2>北</h2>', '<h2>私</h2>')
        self.assertEqual(errors(page(html), check=3), [])


class Check5HaltTime(unittest.TestCase):
    def test_real_halts_with_time_pass(self):
        self.assertEqual(findings(page(real('037'), real('038'))), [])

    def test_missing_time_fails_from_037(self):
        no_time = re.sub(r'\s*<span>\d\d:\d\d</span>', '', real('037'))
        self.assertNotIn('23:55', no_time)
        (f,) = errors(page(no_time), check=5)
        self.assertIn('単位037', f.render())
        self.assertIn('規則06', f.message)

    def test_before_2026_09_05_is_not_required(self):
        self.assertEqual(findings(page(real('029'), real('032'))), [])
        no_time = re.sub(r'\s*<span>\d\d:\d\d</span>', '', real('037'))
        self.assertEqual(errors(page(redate(no_time, '2026.09.04')), check=5), [])
        self.assertTrue(errors(page(redate(no_time, '2026.09.05')), check=5))

    def test_old_halt_redated_to_after_cutoff_fails(self):
        self.assertTrue(errors(page(redate(real('029'), '2026.10.01')), check=5))

    def test_time_in_date_span_and_invalid_time(self):
        same_span = real('037').replace('<span>2026.09.05</span>\n      <span>23:55</span>',
                                        '<span>2026.09.05 23:55</span>')
        self.assertEqual(errors(page(same_span), check=5), [])
        bad = real('037').replace('23:55', '24:00')
        (f,) = errors(page(bad), check=5)
        self.assertIn('24:00', f.message)

    def test_halt_without_halt_class_is_still_a_halt(self):
        no_class = redate(real('029'), '2026.10.01').replace('entry halt', 'entry')
        self.assertTrue(errors(page(no_class), check=5))

    def test_normal_units_need_no_time(self):
        self.assertEqual(errors(page(real('093')), check=5), [])


class Check4Immutable(unittest.TestCase):
    def setUp(self):
        self.base = SOURCE

    def check(self, head):
        return errors(head, self.base, check=4)

    def test_identical_and_new_unit_and_vessel_changes_pass(self):
        self.assertEqual(self.check(SOURCE), [])
        new = ('<article class="entry" id="094">\n    <div class="meta label">\n      <span class="no">No. 094</span>\n'
               '      <span>2026.11.01</span>\n    </div>\n    <h2>新</h2>\n    <p>新しい単位。</p>\n  </article>\n\n  ')
        added = SOURCE.replace('<article class="entry" id="093">', new + '<article class="entry" id="093">', 1)
        self.assertEqual(self.check(added), [])
        vessel = (SOURCE.replace('--moss:   #45654e;', '--moss:   #000;')
                  .replace('<span class="seal">', '<span class="seal" data-x="1">')
                  .replace('const d = ', 'const dd = ').replace('nehan</a>', 'nehan!</a>')
                  )
        self.assertNotEqual(vessel, SOURCE)
        self.assertEqual(self.check(vessel), [])

    def test_number_link_added_to_existing_unit_passes(self):
        linked = SOURCE.replace('<span class="no">No. 093</span>',
                                '<span class="no"><a href="/093/" style="color:inherit;border-bottom:none">No. 093</a></span>')
        self.assertNotEqual(linked, SOURCE)
        self.assertEqual(self.check(linked), [])

    def test_whitespace_only_reflow_passes(self):
        reflowed = SOURCE.replace('<p>北には、関所がない。</p>', '<p>\n      北には、関所がない。\n  </p>')
        self.assertEqual(self.check(reflowed), [])

    def test_changed_title_body_date_number_fail(self):
        title = SOURCE.replace('<h2>思い思い</h2>', '<h2>思い思いに</h2>')
        (f,) = self.check(title)
        self.assertIn('単位092', f.render())
        self.assertIn('題が変更', f.message)

        body = SOURCE.replace('北には、関所がない。', '北には、関所はない。')
        (f,) = self.check(body)
        self.assertIn('単位093『北』', f.render())
        self.assertIn('本文が変更', f.message)
        self.assertIn('6つ目のp', f.message)

        moved = SOURCE.replace('<span>2026.10.27</span>', '<span>2026.10.26</span>', 1)
        (f,) = self.check(moved)
        self.assertIn('単位089', f.render())
        self.assertIn('日付が変更', f.message)
        self.assertIn('2026.10.27', f.message)

        number = SOURCE.replace('<span class="no">No. 091</span>', '<span class="no">No. 910</span>')
        self.assertTrue(any('番号が変更' in f.message for f in self.check(number)))

    def test_changed_paragraph_count_removed_paragraph_and_blockquote(self):
        removed = SOURCE.replace('    <p>北には、関所がない。</p>\n', '')
        self.assertIn('塊', self.check(removed)[0].message)
        quote = SOURCE.replace('<blockquote>damn, failure</blockquote>', '<blockquote>damn, success</blockquote>')
        self.assertIn('単位010', self.check(quote)[0].render())

    def test_deleted_unit_fails(self):
        gone = SOURCE.replace(real('085'), '')
        (f,) = self.check(gone)
        self.assertIn('単位085', f.render())
        self.assertIn('見つかりません', f.message)

    def test_halt_changes_fail(self):
        no_time = re.sub(r'\s*<span>23:55</span>', '', SOURCE)
        self.assertTrue(any('時刻が変更' in f.message for f in self.check(no_time)))
        added_time = SOURCE.replace(real('029'), real('029').replace('<span>2026.08.28</span>',
                                                                      '<span>2026.08.28</span>\n      <span>23:00</span>'))
        self.assertTrue(any('時刻が変更' in f.message for f in self.check(added_time)))
        unhalted = SOURCE.replace(real('029'), real('029').replace('<p class="mark">本日停止</p>', '<p>本日</p>'))
        self.assertTrue(self.check(unhalted))


class Cli(unittest.TestCase):
    """実際に git リポジトリを作り、コマンドとして動かす（終了コードと日本語の出力）。"""

    def git(self, *args):
        subprocess.run(['git', '-C', self.dir, *args], check=True, capture_output=True)

    def run_check(self, *args):
        env = {**os.environ, 'GITHUB_ACTIONS': ''}
        done = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/check_entries.py'),
                               '--file', str(Path(self.dir) / 'index.html'), *args],
                              capture_output=True, text=True, encoding='utf-8', env=env)
        return done.returncode, done.stdout

    def commit(self, html, message):
        (Path(self.dir) / 'index.html').write_text(html, encoding='utf-8')
        self.git('add', 'index.html')
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-m', message)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name
        self.git('init', '-q', '-b', 'main')
        self.commit(SOURCE, 'No. 093')

    def test_clean_run_exits_zero(self):
        code, out = self.run_check('--base', 'HEAD')
        self.assertEqual(code, 0, out)
        self.assertIn('検査した単位: 93', out)
        self.assertIn('失敗なし', out)

    def test_violations_exit_one_and_say_which_unit_which_check_how_many(self):
        broken = SOURCE.replace('北には、関所がない。', '北には、関所はない。私は' + '字' * 260)
        self.commit(broken, 'edit')
        code, out = self.run_check('--base', 'HEAD~1')
        self.assertEqual(code, 1, out)
        self.assertIn('単位093『北』', out)
        self.assertIn('検査1「段落の長さ」', out)
        self.assertIn('字です（上限250字', out)
        self.assertIn('検査4「置かれた単位の不変」', out)

    def test_base_fallbacks_for_new_branch_push(self):
        self.commit(SOURCE.replace('北には、関所がない。', '北には、関所はない。'), 'edit')
        for base in ('0' * 40, '', 'deadbeef' * 5):
            args = ['--base', base] if base else []
            code, out = self.run_check(*args)
            self.assertEqual(code, 1, (base, out))
            self.assertIn('直前のコミット', out)

    def test_no_history_skips_check4_with_notice(self):
        code, out = self.run_check('--base', '0' * 40)
        self.assertEqual(code, 0, out)
        self.assertIn('検査4: スキップ', out)

    def test_github_annotations(self):
        broken = SOURCE.replace('<p>北には、関所がない。</p>', '<p>' + '字' * 251 + '</p>', 1)
        self.commit(broken, 'edit')
        env = {**os.environ, 'GITHUB_ACTIONS': 'true'}
        done = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/check_entries.py'),
                               '--file', str(Path(self.dir) / 'index.html'), '--no-base'],
                              capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertIn('::error file=index.html,line=', done.stdout)
        self.assertIn('title=単位093『北』（2026.10.31） 検査1 段落の長さ::6つ目のpが251字', done.stdout)


if __name__ == '__main__':
    unittest.main()
