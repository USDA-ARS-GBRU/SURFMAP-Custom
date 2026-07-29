
import re
from pathlib import Path
import setuptools


def get_license(): 
    with open('LICENSE') as f:
        license = f.read()

    return license

def get_version():
    init_path = Path(__file__).parent / 'surfmap' / '__init__.py'
    match = re.search(r"^__VERSION__\s*=\s*['\"]([^'\"]+)['\"]",
                       init_path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to find __VERSION__ in surfmap/__init__.py")
    return match.group(1)


install_requires = [
    "freesasa==2.1.0; python_version < '3.12'",
    "freesasa==2.2.1; python_version >= '3.12'",
    "numpy>=1.21.6",
    "pdb2pqr==3.1.0",
    "requests==2.22.0"
]

packages = [
    'surfmap',
    'surfmap.bin',
    'surfmap.tools',
    'surfmap.lib',
    ]

setuptools.setup(
    name='surfmap',
    version=get_version(),
    python_requires='>=3.7',
    license=get_license(),
    packages=packages,
    package_data={'surfmap': ['examples/*']},
    include_package_data=True,
    install_requires=install_requires,
        entry_points={
            'console_scripts': [
                'surfmap=surfmap.bin.surfmap:main',
                '_surfmap_tool=surfmap.tools.SurfmapTools:main',
                'extract_interface=surfmap.bin.extract_interface:main',
                'write_pdb_bs=surfmap.bin.write_pdb_interface:main',
                'pdb2xyzr=surfmap.bin.pdb2xyzr:main',
                'multival_csv2pdb=surfmap.bin.multival_csv_to_pdb:main',
                ]
            }
    )
