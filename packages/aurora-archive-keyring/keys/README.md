# Archive keys

`aurora-debian-archive.asc` is the armored public half of the archive signing key of Aurora's Debian testing packages, and `../../../keys/fingerprint.txt` its fingerprint; `scripts/sign-repository.py --production` signs only with that key.

The committed key is the production **Aurora Debian Archive Signing Key** (`archive@aurorasilicon.org`, fingerprint `EC1D8379B48ADD58D5C8A74E52BF31CC0019FCFE`, Ed25519, valid 5 years). Its private half lives only in the protected `testing-signing` GitHub Actions environment (`DEBIAN_SIGNING_KEY` and `DEBIAN_SIGNING_PASSPHRASE`) and the Owner's private backup.

To rotate the archive signing key in the future:

1. Create the new key pair outside this repository and update the `testing-signing` environment secrets (`DEBIAN_SIGNING_KEY` and `DEBIAN_SIGNING_PASSPHRASE`).
2. Replace `aurora-debian-archive.asc` with the new public half and `keys/fingerprint.txt` with its fingerprint, and bump `aurora-archive-keyring`'s version, so installed systems receive the new key before packages are signed with it.

`development.asc` exists only in a local checkout: `scripts/dev-signing-key` writes it, for images that are built and tested locally and never published. It is ignored by git, and `scripts/sign-repository.py --production` refuses to publish a keyring that contains it.
