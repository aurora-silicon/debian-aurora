#!/usr/bin/env python3
"""Turn a packages/<name> recipe into a Debian source package (.dsc).

Three kinds of recipe exist (docs/packaging.md):

  upstream  a pinned upstream source plus this repository's debian/ directory
  native    every file of the recipe directory is the source (3.0 native)
  rebuild   a pinned Debian testing source package plus Aurora patches
"""
import argparse
import datetime
import email.utils
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAINTAINER = 'Aurora Silicon <noreply@aurorasilicon.org>'
DISTRIBUTION = 'aurora'
VERSION = re.compile(r'(?:(?P<epoch>[0-9]+):)?(?P<upstream>[0-9][A-Za-z0-9.+~]*?)(?:-(?P<revision>[A-Za-z0-9.+~]+))?')
SOURCE = re.compile(r'[a-z0-9][a-z0-9.+-]+')
KINDS = ('upstream', 'native', 'rebuild')


class RecipeError(Exception):
    pass


def load(name, root=ROOT):
    directory = root / 'packages' / name
    if not SOURCE.fullmatch(name) or not (directory / 'recipe.json').is_file():
        raise RecipeError(f'{name}: no recipe')
    recipe = json.loads((directory / 'recipe.json').read_text())
    unknown = set(recipe) - {'source', 'version', 'kind', 'upstream', 'debian', 'network', 'changes', 'alarm',
                             'cross', 'build_on', 'notes'}
    if unknown:
        raise RecipeError(f'{name}: unknown recipe keys {sorted(unknown)}')
    if recipe.get('kind') not in KINDS:
        raise RecipeError(f'{name}: kind must be one of {KINDS}')
    if not SOURCE.fullmatch(recipe.get('source', '')):
        raise RecipeError(f'{name}: invalid source package name')
    match = VERSION.fullmatch(recipe.get('version', ''))
    if not match:
        raise RecipeError(f'{name}: invalid Debian version')
    if recipe['kind'] == 'native' and match['revision']:
        raise RecipeError(f'{name}: a native package version has no Debian revision')
    if recipe['kind'] != 'native' and not match['revision']:
        raise RecipeError(f'{name}: a non-native package version needs a Debian revision')
    if recipe['kind'] == 'upstream' and not isinstance(recipe.get('upstream'), dict):
        raise RecipeError(f'{name}: an upstream recipe names its pinned source')
    if recipe['kind'] == 'rebuild':
        debian = recipe.get('debian') or {}
        if not {'source', 'version'} <= set(debian) <= {'source', 'version', 'suite'} \
                or not VERSION.fullmatch(debian['version']):
            raise RecipeError(f'{name}: a rebuild names the Debian source and version it starts from')
        if debian.get('suite', 'unstable') != 'unstable':
            raise RecipeError(f'{name}: a rebuild starts from testing (the default) or "suite": "unstable"')
        if debian['source'] != recipe['source']:
            raise RecipeError(f'{name}: a rebuild keeps the Debian source name, so its binaries replace Debian\'s')
        if not recipe['version'].startswith(debian['version'] + '+aurora'):
            raise RecipeError(f'{name}: a rebuild version is the Debian version plus +auroraN')
    if not isinstance(recipe.get('changes'), str) or not recipe['changes'].strip():
        raise RecipeError(f'{name}: say what this build changes in "changes"')
    if recipe.get('build_on', 'arm64') not in ('arm64', 'amd64'):
        raise RecipeError(f'{name}: build_on is arm64 (the default) or amd64')
    if not isinstance(recipe.get('network', False), bool):
        raise RecipeError(f'{name}: network is true or false')
    recipe['name'] = name
    recipe['directory'] = directory
    return recipe


def upstream_version(version):
    match = VERSION.fullmatch(version)
    return match['upstream']


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, digest, cache):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (digest + '-' + url.rstrip('/').rsplit('/', 1)[-1].split('?')[0])
    if target.is_file() and sha256(target) == digest:
        return target
    # Concurrent builds may fetch the same archive; each writes its own file.
    descriptor, name = tempfile.mkstemp(prefix=target.name + '.', suffix='.part', dir=cache)
    partial = Path(name)
    request = urllib.request.Request(url, headers={'User-Agent': 'debian-aurora-builder'})
    with urllib.request.urlopen(request, timeout=300) as response, os.fdopen(descriptor, 'wb') as output:
        shutil.copyfileobj(response, output)
    observed = sha256(partial)
    if observed != digest:
        partial.unlink()
        raise RecipeError(f'{url}: sha256 {observed}, expected {digest}')
    partial.chmod(0o644)
    partial.rename(target)
    return target


def pinned(upstream, sources):
    """The URL and digest of an upstream source: a sources.json pin or an explicit URL."""
    if 'pin' in upstream:
        record = sources.get(upstream['pin'])
        if not record or not re.fullmatch(r'[0-9a-f]{40}', record.get('commit', '')):
            raise RecipeError(f'unknown or unpinned source {upstream["pin"]}')
        slug = record['repository'].removeprefix('https://github.com/').removesuffix('.git')
        if slug == record['repository']:
            raise RecipeError(f'{upstream["pin"]}: only GitHub pins have a codeload archive')
        return f'https://codeload.github.com/{slug}/tar.gz/{record["commit"]}', record['sha256']
    if set(upstream) - {'url', 'sha256', 'strip'} or not re.fullmatch(r'[0-9a-f]{64}', upstream.get('sha256', '')):
        raise RecipeError('an upstream URL needs its sha256')
    return upstream['url'], upstream['sha256']


def git_checkout(upstream, sources, destination):
    """A pinned commit with its submodules, for sources whose archive lacks them."""
    record = sources.get(upstream['git'])
    if not record or not re.fullmatch(r'[0-9a-f]{40}', record.get('commit', '')):
        raise RecipeError(f'unknown or unpinned source {upstream["git"]}')
    subprocess.run(['git', 'init', '-q', str(destination)], check=True)
    subprocess.run(['git', '-C', str(destination), 'fetch', '-q', '--depth', '1', record['repository'],
                    record['commit']], check=True)
    subprocess.run(['git', '-C', str(destination), 'checkout', '-q', 'FETCH_HEAD'], check=True)
    head = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    if head != record['commit']:
        raise RecipeError(f'{upstream["git"]}: fetched {head}, expected {record["commit"]}')
    if upstream.get('submodules'):
        subprocess.run(['git', '-C', str(destination), 'submodule', 'update', '-q', '--init', '--recursive',
                        '--depth', '1'], check=True)
    for path in destination.rglob('.git'):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def compression(path):
    """The orig tarball suffix dpkg-source expects for this archive's compression."""
    magic = Path(path).read_bytes()[:6]
    for prefix, suffix in ((b'\x1f\x8b', '.tar.gz'), (b'\xfd7zXZ\x00', '.tar.xz'), (b'BZh', '.tar.bz2'),
                           (b'\x28\xb5\x2f\xfd', '.tar.zst')):
        if magic.startswith(prefix):
            return suffix
    raise RecipeError(f'{path}: not a compressed tar archive')


def unpack(archive, destination, strip=1):
    """Extract an archive, dropping its leading directory, refusing escaping members."""
    destination.mkdir(parents=True)
    with tarfile.open(archive) as stream:
        members = []
        for member in stream.getmembers():
            parts = Path(member.name).parts[strip:]
            if not parts:
                continue
            member.name = str(Path(*parts))
            members.append(member)
        stream.extractall(destination, members=members, filter='tar')


def changelog_entry(recipe, epoch):
    stamp = email.utils.format_datetime(datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc))
    lines = [f'{recipe["source"]} ({recipe["version"]}) {DISTRIBUTION}; urgency=medium', '']
    for paragraph in recipe['changes'].strip().split('\n'):
        lines += textwrap.wrap(paragraph.strip(), 78, initial_indent='  * ', subsequent_indent='    ')
    lines += ['', f' -- {MAINTAINER}  {stamp}', '']
    return '\n'.join(lines) + '\n'


def source_date_epoch(recipe):
    if os.environ.get('SOURCE_DATE_EPOCH'):
        return int(os.environ['SOURCE_DATE_EPOCH'])
    result = subprocess.run(['git', '-C', str(ROOT), 'log', '-1', '--format=%ct', '--', str(recipe['directory'])],
                            capture_output=True, text=True)
    return int(result.stdout.strip() or 0) or int(datetime.datetime(2026, 11, 20,
                                                                    tzinfo=datetime.timezone.utc).timestamp())


def copy_tree(source, destination, skip=()):
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        # Bytecode from running a recipe's tests in place is never source.
        if relative.parts[0] in skip or '__pycache__' in relative.parts:
            continue
        target = destination / relative
        if path.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(os.readlink(path))
        elif path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def debian_source(recipe, base, work, cache):
    """Download and unpack the pinned Debian source package with apt, which checks the archive signature."""
    apt = work / 'apt'
    for directory in ('lists/partial', 'archives/partial', 'etc/preferences.d', 'etc/apt.conf.d'):
        (apt / directory).mkdir(parents=True, exist_ok=True)
    (apt / 'etc/sources.list').write_text(
        f'deb-src [signed-by={base["keyring"]} check-valid-until=no] {base["mirror"]} '
        f'{recipe["debian"].get("suite", base["suite"])} '
        + ' '.join(base['components']) + '\n')
    options = ['-o', f'Dir::Etc={apt / "etc"}', '-o', f'Dir::State::Lists={apt / "lists"}',
               '-o', f'Dir::Cache={apt}', '-o', 'Dir::Etc::SourceParts=-', '-o', 'APT::Sandbox::User=root',
               '-o', 'Acquire::Check-Valid-Until=false', '-o', 'Debug::NoLocking=1']
    subprocess.run(['apt-get', *options, '-qq', 'update'], check=True)
    download_dir = cache / 'debian' / recipe['debian']['source']
    download_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(['apt-get', *options, '-qq', 'source', '--download-only',
                    f'{recipe["debian"]["source"]}={recipe["debian"]["version"]}'], cwd=download_dir, check=True)
    upstream = upstream_version(recipe['debian']['version'])
    dsc = download_dir / f'{recipe["debian"]["source"]}_{recipe["debian"]["version"].split(":")[-1]}.dsc'
    tree = work / f'{recipe["source"]}-{upstream}'
    subprocess.run(['dpkg-source', '--no-check', '-x', str(dsc), str(tree)], check=True,
                   stdout=subprocess.DEVNULL)
    for path in download_dir.glob(f'{recipe["source"]}_{upstream}.orig*'):
        shutil.copy2(path, work / path.name)
    return tree


def prepare(name, work, root=ROOT, cache=None, components=()):
    recipe = load(name, root)
    cache = cache or root / 'cache'
    sources = json.loads((root / 'sources.json').read_text())
    base = json.loads((root / 'images/base.json').read_text())
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    upstream = upstream_version(recipe['version'])
    tree = work / f'{recipe["source"]}-{upstream}'
    directory = recipe['directory']
    if recipe['kind'] == 'native':
        tree.mkdir()
        copy_tree(directory, tree, skip=('recipe.json',))
        (tree / 'recipe.json').unlink(missing_ok=True)
        fmt = '3.0 (native)'
    elif recipe['kind'] == 'upstream':
        spec = recipe['upstream']
        orig = work / f'{recipe["source"]}_{upstream}.orig.tar.gz'
        if 'git' in spec:
            checkout = work / 'checkout'
            git_checkout(spec, sources, checkout)
            with tarfile.open(orig, 'w:gz') as archive:
                archive.add(checkout, arcname=f'{recipe["source"]}-{upstream}',
                            filter=lambda info: info.replace(uid=0, gid=0, uname='', gname='', mtime=0, deep=False))
            checkout.rename(tree)
        else:
            url, digest = pinned(spec, sources)
            archive = download(url, digest, cache / 'sources')
            orig = work / f'{recipe["source"]}_{upstream}.orig{compression(archive)}'
            shutil.copy2(archive, orig)
            unpack(orig, tree, spec.get('strip', 1))
            # A pin's extra sources become Debian component tarballs
            # (orig-<key>), which dpkg-source unpacks in <key>/.
            for key, extra in (sources[spec['pin']].get('extra_sources') or {}).items() if 'pin' in spec else ():
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', key):
                    raise RecipeError(f'{name}: extra source {key} is not a valid component name')
                component = download(extra['source_url'], extra['sha256'], cache / 'sources')
                target = work / f'{recipe["source"]}_{upstream}.orig-{key}{compression(component)}'
                shutil.copy2(component, target)
                unpack(target, tree / key)
            for key, component in components:
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', key):
                    raise RecipeError(f'{name}: component {key} is not a valid component name')
                comp_path = Path(component).resolve()
                target = work / f'{recipe["source"]}_{upstream}.orig-{key}{compression(comp_path)}'
                shutil.copy2(comp_path, target)
                unpack(target, tree / key)
        if (tree / 'debian').exists():
            shutil.rmtree(tree / 'debian')
        copy_tree(directory / 'debian', tree / 'debian')
        key = spec.get('pin') or spec.get('git')
        if key:
            # debian/rules reads the pinned identity instead of repeating it.
            record = sources[key]
            (tree / 'debian/aurora-pin').write_text(
                f'repository={record["repository"]}\ncommit={record["commit"]}\nversion={record.get("version", "")}\n')
        fmt = '3.0 (quilt)'
    else:
        tree = debian_source(recipe, base, work, cache)
        packaging = directory / 'packaging.patch'
        if packaging.is_file():
            # stdout is the .dsc path build-package reads; patch reports on stderr.
            subprocess.run(['patch', '-p1', '--no-backup-if-mismatch', '-i', str(packaging)], cwd=tree, check=True,
                           stdout=sys.stderr)
        patches = sorted((directory / 'patches').glob('*.patch')) if (directory / 'patches').is_dir() else []
        if patches:
            series = tree / 'debian/patches/series'
            series.parent.mkdir(parents=True, exist_ok=True)
            existing = series.read_text() if series.exists() else ''
            names = []
            for patch in patches:
                target = 'aurora-' + patch.name
                shutil.copy2(patch, tree / 'debian/patches' / target)
                names.append(target)
            series.write_text(existing + ('' if not existing or existing.endswith('\n') else '\n')
                              + '\n'.join(names) + '\n')
        fmt = (tree / 'debian/source/format').read_text().strip()
    (tree / 'debian/source').mkdir(parents=True, exist_ok=True)
    (tree / 'debian/source/format').write_text(fmt + '\n')
    entry = changelog_entry(recipe, source_date_epoch(recipe))
    changelog = tree / 'debian/changelog'
    previous = changelog.read_text() if recipe['kind'] == 'rebuild' and changelog.exists() else ''
    changelog.write_text(entry + previous if previous else entry.rstrip('\n') + '\n')
    environment = dict(os.environ, SOURCE_DATE_EPOCH=str(source_date_epoch(recipe)))
    subprocess.run(['dpkg-source', '-b', tree.name], cwd=work, check=True, env=environment,
                   stdout=subprocess.DEVNULL)
    dsc = work / f'{recipe["source"]}_{recipe["version"].split(":")[-1]}.dsc'
    if not dsc.is_file():
        raise RecipeError(f'{name}: dpkg-source did not produce {dsc.name}')
    return dsc


def fetch_upstream(name, root=ROOT, cache=None):
    """Download and verify a recipe's pinned upstream archive; return (commit, path, suffix)."""
    recipe = load(name, root)
    if recipe['kind'] != 'upstream' or 'pin' not in recipe.get('upstream', {}):
        raise RecipeError(f'{name}: fetch requires a pinned upstream recipe')
    cache = cache or root / 'cache'
    sources = json.loads((root / 'sources.json').read_text())
    url, digest = pinned(recipe['upstream'], sources)
    archive = download(url, digest, cache / 'sources').resolve()
    commit = sources[recipe['upstream']['pin']]['commit']
    return commit, archive, compression(archive)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('prepare', help='write the source package and print its .dsc path')
    command.add_argument('name')
    command.add_argument('work', type=Path)
    command.add_argument('--component', action='append', default=[], metavar='NAME=ARCHIVE',
                         help='attach an additional 3.0 (quilt) component tarball (orig-NAME)')
    command = commands.add_parser('fetch', help='download the pinned upstream archive and print COMMIT PATH')
    command.add_argument('name')
    command = commands.add_parser('field', help='print one recipe field (for build-package)')
    command.add_argument('name')
    command.add_argument('field')
    command = commands.add_parser('check', help='validate every recipe')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            components = []
            for item in args.component:
                if '=' not in item:
                    raise RecipeError(f'--component expects NAME=ARCHIVE, got {item!r}')
                components.append(tuple(item.split('=', 1)))
            print(prepare(args.name, args.work.resolve(), components=components))
        elif args.command == 'fetch':
            commit, archive, suffix = fetch_upstream(args.name)
            print(f'{commit} {archive} {suffix}')
        elif args.command == 'field':
            value = load(args.name).get(args.field)
            print(json.dumps(value) if isinstance(value, (dict, list, bool)) or value is None else value)
        else:
            names = sorted(path.parent.name for path in (ROOT / 'packages').glob('*/recipe.json'))
            for name in names:
                load(name)
            print(f'{len(names)} recipes valid')
    except RecipeError as error:
        sys.exit(f'recipe: {error}')


if __name__ == '__main__':
    main()
