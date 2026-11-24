"""The log-benchmark harness (experiments/log_benchmark.py). No data file is needed here."""
import pytest

from experiments.log_benchmark import PINS, PUBLISHED, SETTINGS, STAR, ReferenceSpell, accuracy, spell_tokens
from hpcrd.templates import TemplateReader


def test_accuracy_is_the_benchmarks_definition():
    # the benchmark paper's own example: [E1, E2, E2] parsed as [E1, E4, E5] is 1/3
    assert accuracy(['a', 'b', 'c'], ['E1', 'E2', 'E2']) == pytest.approx(1 / 3)
    assert accuracy(['a', 'b', 'b'], ['E1', 'E2', 'E2']) == 1.0
    assert accuracy(['a', 'a', 'a'], ['E1', 'E2', 'E2']) == 0.0      # one group over two events


def test_settings_cover_the_sixteen_systems_and_the_pinned_files():
    assert set(SETTINGS) == set(PUBLISHED) and len(SETTINGS) == 16
    assert {name.split('_2k')[0] for name in PINS['files']} == set(SETTINGS)
    # Table IV prints 0.751 as Spell's average. Its sixteen printed values average 0.793.
    assert sum(spell for spell, _ in PUBLISHED.values()) / 16 == pytest.approx(0.793, abs=0.0005)
    assert sum(drain for _, drain in PUBLISHED.values()) / 16 == pytest.approx(0.866, abs=0.0005)


def test_the_rewritten_reference_groups_the_papers_example():
    lines = [spell_tokens(s) for s in ("Command Failed on: node-127", "Command Failed on: node-235 node-236",
                                       "Temperature (41C) exceeds warning threshold")]
    assert ReferenceSpell(0.5).parse(lines) == [f"Command Failed on {STAR}", f"Command Failed on {STAR}",
                                                "Temperature (41C) exceeds warning threshold"]


@pytest.mark.parametrize('first, second, want', [
    (['x', 'a'], ['y', 'b'], ['x', STAR]),      # the line shares one token with each; the older type takes it
    (['y', 'b'], ['x', 'a'], [STAR, 'b']),
])
def test_a_tie_goes_to_the_older_type_whatever_the_pattern_names_are(first, second, want):
    reader = TemplateReader(0.5, parameter=STAR)
    reader.read(first)
    reader.read(second)
    name, joined, _gaps = reader.read(['x', 'b'])
    assert joined and reader.template(name) == want
    assert len(reader.node.patterns) - len(reader.node.retired) == 2


def test_a_line_that_holds_the_placeholder_matches_a_templates_placeholder():
    reader = TemplateReader(0.7, parameter=STAR)
    reader.read(['Receiving', 'block', STAR, 'src', STAR])
    name, joined, _gaps = reader.read(['Receiving', 'block', STAR, 'src', STAR])
    assert joined and reader.node.frequency(name) == 2 and not reader.node.retired
