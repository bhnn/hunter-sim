from setuptools import setup, find_packages

setup(
    name='hunter-sim',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'pyyaml',
    ],
    entry_points={
        'console_scripts': [
            'hunter-sim = hunter_sim.main:main',
        ],
    },
)