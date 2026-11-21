# Archive keys

`aurora-debian-archive.asc` is the armored public half of Aurora Debian's archive signing key, and `../../../keys/fingerprint.txt` its fingerprint; `scripts/sign-repository.py --production` signs only with that key.

**The key committed now is a temporary test key** (user ID "Aurora Debian archive key (TEMPORARY test key, replace before release)", expires 2027-11-21). It exists so the whole pipeline can be tested end to end. Its private half is kept outside git, in `cache/archive-signing/` of the checkout that created it. Before the first public release the Aurora maintainers replace it with their own key:

1. Create the key pair outside this repository; keep the private half only in the `testing-signing` environment's `DEBIAN_SIGNING_KEY` secret (with `DEBIAN_SIGNING_PASSPHRASE`).
2. Replace `aurora-debian-archive.asc` with the new public half and `keys/fingerprint.txt` with its fingerprint, and bump `aurora-archive-keyring`'s version, so installed systems receive the new key before packages are signed with it.
3. Delete the temporary key's private half.

`development.asc` exists only in a local checkout: `scripts/dev-signing-key` writes it, for images that are built and tested locally and never published. It is ignored by git, and `scripts/sign-repository.py --production` refuses to publish a keyring that contains it.
