# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

# for test files, silence irrelevant and noisy pylint warnings
# pylint: disable=no-self-use,protected-access,missing-docstring,too-many-public-methods

import re
import unittest

from antismash.common import html_renderer as renderer
from antismash.config import build_config


def _verify_html_tags_match(html):
    regex = re.compile(r"<(/?)(.*?)>")
    matches = regex.findall(html)
    self_closing_tags = {"br", "hr", "img", "input", "link", "meta", "embed"}
    stack = []
    print(html)
    assert matches
    for closing, tag in matches:
        tag = tag.split()[0]
        if tag in self_closing_tags:
            continue
        print(closing, tag)
        if closing:
            assert stack and stack[-1] == tag, "extra </%s>" % tag
            print("closed", stack[-1])
            stack.pop()
        else:
            stack.append(tag)
            print("opened", stack[-1])
    print(stack)
    assert not stack, "unclosed: %s" % ", ".join(stack)


class TestHTMLMatcher(unittest.TestCase):
    def test_simple(self):
        _verify_html_tags_match("<div>thing</div>")
        with self.assertRaises(AssertionError):
            _verify_html_tags_match("<div>thing")
        with self.assertRaises(AssertionError):
            _verify_html_tags_match("thing</div>")

    def test_self_closed(self):
        cases = ["<br>", "<hr>", "<img src='stuff'>", "<input stuff>", "<link>",
                 "<meta>", "<embed>"]
        for html in cases:
            _verify_html_tags_match(html)


class TestSafeSelector(unittest.TestCase):
    def test_no_replacement(self):
        assert renderer._safe_selector("test") == "test"

    def test_period(self):
        assert renderer._safe_selector("some_name.3") == "some_name-3"

    def test_colon(self):
        assert renderer._safe_selector("some:name-3") == "some-name-3"

    def test_combo(self):
        assert renderer._safe_selector("some:name.3") == "some-name-3"


class TestCollapser(unittest.TestCase):
    def test_simple(self):
        for level in ["all", "candidate", "protocluster", "cds", "none"]:
            html = str(renderer.collapser_start("dummy", level)) + str(renderer.collapser_end())
            _verify_html_tags_match(html)
            assert "collapser-target-dummy" in html
            assert "collapser-level-%s" % level in html

    def test_safe_classes(self):
        html = str(renderer.collapser_start("some:name.3", "all")) + str(renderer.collapser_end())
        _verify_html_tags_match(html)
        assert "some:name.3" not in html
        assert "collapser-target-some-name-3" in html

    def test_bad_level(self):
        with self.assertRaisesRegex(ValueError, "unknown collapser level"):
            renderer.collapser_start("dummy", "invalid")


class TestDocsLink(unittest.TestCase):
    def setUp(self):
        self.url = build_config([]).urls.docs_baseurl

    def test_no_subtarget(self):
        result = renderer.docs_link("label")
        assert isinstance(result, renderer.Markup)
        expected = "<a class='external-link' href='%s' target='_blank'>label</a>" % self.url
        assert str(result) == expected

    def test_subtarget(self):
        target = "modules/modulename"
        result = renderer.docs_link("label", target)
        assert isinstance(result, renderer.Markup)
        url = self.url + target
        expected = "<a class='external-link' href='%s' target='_blank'>label</a>" % url
        assert str(result) == expected


class TestSequences(unittest.TestCase):
    def test_unclassed(self):
        result = renderer.spanned_sequence("ABCD", {})
        assert result == "".join(f"<span>{char}</span>" for char in "ABCD")

    def test_classed(self):
        result = renderer.spanned_sequence("ABA", {
            "A": "aa",
            "B": "bbbb",
        })
        a_chunk = '<span class="aa">A</span>'
        b_chunk = '<span class="bbbb">B</span>'
        assert result == f"{a_chunk}{b_chunk}{a_chunk}"

    def test_mixed(self):
        result = renderer.spanned_sequence("ABCD", {
            "A": "aa",
            "D": "some-class",
        })
        a_chunk = '<span class="aa">A</span>'
        b_chunk = '<span>B</span>'
        c_chunk = '<span>C</span>'
        d_chunk = '<span class="some-class">D</span>'
        assert result == f"{a_chunk}{b_chunk}{c_chunk}{d_chunk}"

    def test_invalid(self):
        for char in "<> ?!+": # indicative, not exhaustive
            with self.assertRaisesRegex(ValueError, "invalid character in HTML class"):
                renderer.spanned_sequence("A", {"A": f"a{char}b"})

    def test_substitutions(self):
        result = renderer.spanned_sequence("ABC", {}, substitutions={
            "A": "123",
            "C": "456",
        })
        a_chunk = '<span>123</span>'
        b_chunk = '<span>B</span>'
        c_chunk = '<span>456</span>'
        assert result == f"{a_chunk}{b_chunk}{c_chunk}"

    def test_ripps_dehydration(self):
        result = renderer.coloured_ripp_sequence("TISC", dehydrate=True)
        assert result == "".join([
            '<span class="dhb">Dhb</span>',
            '<span>I</span>',
            '<span class="dha">Dha</span>',
            '<span class="cys">Cys</span>',
        ])

    def test_ripp_clean(self):
        result = renderer.coloured_ripp_sequence("TISC", dehydrate=False)
        assert result == "".join([
            '<span class="dhb">T</span>',
            '<span>I</span>',
            '<span class="dha">S</span>',
            '<span class="cys">C</span>',
        ])
        # and that dehydration is not the default
        assert result == renderer.coloured_ripp_sequence("TISC")
