#!/usr/bin/env python3
"""Print a public key whose private half is never written down.

The secure-flavour Stage 1 verifies with the owner's key once aurora-secboot
fills its key block; until then it carries this key, so an unfilled image
verifies nothing (as alarm-aurora's aura recipe does).
"""
import os
import sys

sys.path.insert(0, 'tools')
import secboot_sign  # noqa: E402

sys.stdout.buffer.write(secboot_sign.pubkey(os.urandom(32)))
