"""Any text, any settings, from the command line. Prints what every node ends up holding.

    ./run.sh examples/explore.py E4 span=sequence markers=. slots=gap values=sequence recall_threshold=0.5 inside=1
    ./run.sh examples/explore.py "the cat sat . the dog sat ." span=sequence markers=.

The first argument is a key of TEXTS or the text itself. Settings are name=value (hpcrd.modeler.Settings).
"""
import dataclasses
import sys

from hpcrd.modeler import Modeler, Settings
from hpcrd.show import dump_node, print_result, print_sequence, print_step

TEXTS = {
    'A': ("the cat sat on the mat . the dog sat on the mat . the cat sat on the rug . "
          "a dog sat on the rug . the bird sat on the mat ."),
    'E1': "the cat sat on the mat . the dog sat on the mat . the bird sat on the mat .",
    'E2': ("the old cat sat on the mat by the door . the old dog sat on the mat by the door . "
           "the old bird sat on the mat by the door ."),
    'E3': ("the cat sat on the mat . the dog sat on the mat . the cat sat on the rug . the dog sat on the rug . "
           "when the cat is happy it purrs . when the dog is happy it barks . "
           "when the cat is happy it purrs . when the dog is happy it barks ."),
    'E3short': ("the cat says meow . the dog says woof . the cat says meow . the dog says woof ."),
    'E4': ("show flights from boston to denver . show flights from dallas to denver . "
           "show me flights from boston to denver . show flights from new york to denver . "
           "show flights from los angeles to denver ."),
    'N1': ("the cat sat on the mat . the dog sat on the mat . "
           "we saw the cat near the old barn . we saw the dog near the old barn . "
           "the cat sat by a warm fire . the dog sat by a warm fire . "
           "the bird sat on the mat . we saw the bird near the old barn . the bird sat by a warm fire ."),
    'R1': ("the big dog sat on the mat . the small cat sat on the mat . the big cat sat on the mat . "
           "we saw the big dog near the old barn . we saw the small cat near the old barn . "
           "we saw the small dog near the old barn ."),
    'N2': ("the cat sat on the mat . the dog sat on the mat . "
           "we saw the cat near the old barn . we saw the dog near the old barn . "
           "we walked to the park . we walked to the shop . "
           "the bird sat on the mat . we saw the bird near the old barn . the dog sat on the rug ."),
    'E5': ("the cat sat on the mat . the dog sat on the mat . a dog sat on the rug . "
           "the cat chased the dog away . a dog chased the cat away . a cat sat on the rug . "
           "the dog chased a cat away ."),
}


def run(text, verbose=True, **kw):
    s = Settings(**kw)
    m = Modeler(s)

    def stretch(res):
        a, b = res['stretch']
        print(f"stretch {a}..{b - 1}: {' '.join(m.tokens[a:b])}")
        print_result(res, m, m.tokens[a:b])

    for token in text.split():
        step = m.feed(token)
        if not verbose:
            continue
        if s.span == 'window':
            if step['parts']:
                print_step(step, m, readings=verbose == 2)
        elif s.span == 'sequence':
            print_sequence(step, m, readings=verbose == 2)
        else:
            for res in step['stretches']:
                stretch(res)
    for res in m.finish():
        if s.span == 'sequence':
            print_sequence(m.trace[-1], m, readings=verbose == 2)
        else:
            stretch(res)
    print()
    dump_node(m.node0, 'node_0', limit=0)
    if m.reader is not None:
        dump_node(m.reader.node, 'templates')
    print('  VARs:', m.var_count)
    dump_node(m.node1a, 'node_1a')
    dump_node(m.node1b, 'node_1b', m.node1a)
    dump_node(m.node2a, 'node_2a')
    dump_node(m.node2b, 'node_2b', m.node1a)
    if m.node1t is not None:
        dump_node(m.node1t, 'node_1t')
    return m


if __name__ == '__main__':
    args = dict(a.split('=', 1) for a in sys.argv[2:])
    verbose = int(args.pop('verbose', 1))
    kinds = {f.name: f.type for f in dataclasses.fields(Settings)}
    for key, value in args.items():
        kind = kinds[key]
        if kind in (bool, 'bool'):
            args[key] = value in ('1', 'True', 'true')
        elif kind in (int, 'int'):
            args[key] = int(value)
        elif kind in (float, 'float'):
            args[key] = float(value)
        elif kind in (tuple, 'tuple'):
            args[key] = tuple(value.split(','))
    run(TEXTS.get(sys.argv[1], sys.argv[1]), verbose=verbose, **args)
