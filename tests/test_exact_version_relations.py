"""Packages that depend on another recipe's packages at exactly their own version move with it.

A relation such as `libgl1-mesa-dri (= ${source:Version})` names this package's
own version. When another recipe builds libgl1-mesa-dri, apt can only install
the pair if both recipes carry the same version: otherwise the dependant is held
back and never reaches a system. mesa-aurora-fex-guest and aurora-flatpak-gl
depend on the host mesa's packages this way.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELATION_FIELDS = ('Depends', 'Pre-Depends', 'Recommends')
EXACT = re.compile(r'([a-z0-9][a-z0-9+.-]+)(?::[a-z0-9-]+)?\s*\(\s*=\s*\$\{(?:source|binary):Version\}\s*\)')


def control_fields(text):
    """Each stanza of a debian/control file as {field: value}, continuation lines joined."""
    stanzas = []
    for block in re.split(r'\n\s*\n', text):
        fields, name = {}, None
        for line in block.splitlines():
            if line.startswith('#'):
                continue
            if line[:1] in (' ', '\t') and name:
                fields[name] += ' ' + line.strip()
            elif ':' in line:
                name, value = line.split(':', 1)
                fields[name.strip()] = value.strip()
        if fields:
            stanzas.append(fields)
    return stanzas


def recipes():
    """{recipe: (version, binary packages, exact-version relations)} for each recipe with a debian/control."""
    found = {}
    for control in sorted(ROOT.glob('packages/*/debian/control')):
        name = control.parent.parent.name
        version = json.loads((control.parent.parent / 'recipe.json').read_text())['version']
        stanzas = control_fields(control.read_text())
        binaries = {s['Package'] for s in stanzas if 'Package' in s}
        exact = {m.group(1) for s in stanzas for field in RELATION_FIELDS for m in EXACT.finditer(s.get(field, ''))}
        found[name] = (version, binaries, exact)
    return found


class ExactVersionRelationTests(unittest.TestCase):
    def test_exact_version_relations_name_the_same_version(self):
        found = recipes()
        builder = {binary: name for name, (_, binaries, _) in found.items() for binary in binaries}
        checked = 0
        for name, (version, binaries, exact) in found.items():
            for package in sorted(exact - binaries):
                other = builder.get(package)
                if other is None:
                    continue
                checked += 1
                with self.subTest(recipe=name, depends_on=package, built_by=other):
                    self.assertEqual(version, found[other][0])
        # The FEX guest and the Flatpak GL extension depend on the host mesa's packages.
        self.assertGreaterEqual(checked, 4)

    def test_control_parser_reads_continuation_lines(self):
        stanzas = control_fields('Source: src\n\nPackage: liba\nDepends:\n libb (= ${source:Version}),\n libc\n')
        self.assertEqual(stanzas[1]['Package'], 'liba')
        self.assertEqual({m.group(1) for m in EXACT.finditer(stanzas[1]['Depends'])}, {'libb'})


if __name__ == '__main__':
    unittest.main()
