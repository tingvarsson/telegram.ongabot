"""The module defines the version(s) of ONGAbot.

Between releases this carries a "+dev" build-metadata suffix on the last released
version (e.g. "1.2.0+dev"), marking a development build. `make release` strips the
suffix to produce the clean release; `make post-release` re-adds it to the new base.
"""

__version__ = "1.3.0"
