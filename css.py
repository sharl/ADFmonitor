# -*- coding: utf-8 -*-
from tinycss2 import parse_stylesheet, serialize, parse_declaration_list
import requests


class CSS:
    def __init__(self, url):
        with requests.get(url, timeout=10) as r:
            css_data = r.content.decode('utf8')
            self.css = self.parse(css_data)

    def parse(self, css: str) -> dict:
        result = {}
        for rule in parse_stylesheet(
                css,
                skip_whitespace=True,
                skip_comments=True,
        ):
            if rule.type != 'qualified-rule':
                continue

            for selector in serialize(rule.prelude).split(','):
                selector = selector.strip()
                declarations = {}
                for decl in parse_declaration_list(
                        rule.content,
                        skip_whitespace=True,
                        skip_comments=True,
                ):
                    if decl.type == 'declaration':
                        value = serialize(decl.value).strip()
                        declarations[decl.name] = value

                if selector in result:
                    result[selector].update(declarations)
                else:
                    result[selector] = declarations

        return result

    def selectors(self, class_name):
        parts = class_name.split()

        for i in range(len(parts), 0, -1):
            yield '.' + '.'.join(parts[:i])

    def get_style(self, class_name, prop):
        for selector in self.selectors(class_name):
            value = self.css.get(selector, {}).get(prop)
            if value is not None:
                return value


TENGOKU_CSS_URL = 'https://cache.hiroba.dqx.jp/dq_resource/css/game/tengoku.css'


if __name__ == '__main__':
    css = CSS(TENGOKU_CSS_URL)

    tengoku_width = css.get_style('tengoku is_open mt15', 'width')
    tengoku_height = css.get_style('tengoku is_open mt15', 'height')
    print(f'{tengoku_width=} {tengoku_height=}')

    inferno_width = css.get_style('f-inferno mt20 is-open', 'width')
    inferno_height = css.get_style('f-inferno mt20 is-open', 'height')
    print(f'{inferno_width=} {inferno_height=}')

    konmeiko_width = css.get_style('konmeiko mt20 is-open', 'width')
    konmeiko_height = css.get_style('konmeiko mt20 is-open', 'height')
    print(f'{konmeiko_width=} {konmeiko_height=}')

    ikai_width = css.get_style('ikai mt20 is-open', 'width')
    ikai_height = css.get_style('ikai mt20 is-open', 'height')
    print(f'{ikai_width=} {ikai_height=}')

    jikken_width = css.get_style('jikken mt20 is-open', 'width')
    jikken_height = css.get_style('jikken mt20 is-open', 'height')
    print(f'{jikken_width=} {jikken_height=}')
