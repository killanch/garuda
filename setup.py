# -*- coding:utf-8 -*-

import os
from setuptools  import setup
import pip

with open('requirements.txt') as f:
    install_requires = f.read().strip().split('\n')

setup(
    name='garuda',
    version='0.0.1',
    author='Christophe Serafin',
    packages=[  'garuda',
                'garuda.plugins',
                'garuda.plugins.authentication',
                'garuda.plugins.storage',
                'garuda.plugins.permissions',
                'garuda.channels',
                'garuda.channels.rest',
                'garuda.core',
                'garuda.core.channels',
                'garuda.core.controllers',
                'garuda.core.lib',
                'garuda.core.models',
                'garuda.core.plugins'],

    author_email='christophe.serafin@nuagenetworks.net, antoine@nuagenetworks.net',
    description='Garuda is the future. No more. No less.',
    long_description=open('README.md').read(),
    install_requires=install_requires,
    dependency_links=[
        'git+https://github.com/nuagenetworks/bambou.git#egg=bambou',
        'git+https://github.com/primalmotion/pypred.git#egg=pypred'
    ],
    license='TODO',
    url='TODO'
)
