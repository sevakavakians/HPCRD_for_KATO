"""The scoring of the baseline parsers (experiments/baselines.py). No data file is needed here."""
from experiments.baselines import Spell, gaps, score


def test_the_first_template_is_a_rule_like_any_other():
    # Templates are numbered from 0, and the judge skips a part that has no rule. Until 26 Nov 2026 the
    # number itself was passed as the rule, so every sentence that joined template 0 was scored as
    # having no rule at all.
    data = [('a b c'.split(), []), ('a x c'.split(), [('kind', 1, 2)])]
    parser, spans, member = Spell(0.5), [], []
    for tokens, _slots in data:
        k, joined = parser.add(tokens)
        member.append(k)
        spans.append(gaps(tokens, parser.constants(k)) if joined else [])
    assert member == [0, 0] and spans == [[], [(1, 2)]]
    slot_side, var_side = score(data, spans, member)
    assert slot_side == {'one VAR, exactly': 1} and var_side == {'exactly a slot': 1}


def test_a_sentence_with_no_variable_has_no_rule_for_its_slots():
    data = [('a b c'.split(), [('kind', 1, 2)])]
    slot_side, var_side = score(data, [[]], [0])
    assert slot_side == {'no rule for the sentence': 1} and not var_side
