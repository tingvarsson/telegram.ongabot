#!/usr/bin/env python
"""The setup and build script for the ON/GA Telegram bot."""

import setuptools
import versioneer

with open("README.md", "r") as fh:
    long_description = fh.read()
with open("requirements.txt", "r") as fh:
    requirements = [line.strip() for line in fh]

setuptools.setup(
    name="ongabot",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    author="Thomas Ingvarsson",
    author_email="ingvarsson.thomas@gmail.com",
    description="The one and only ON/GA Telegram bot.",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=requirements,
)
