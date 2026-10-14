# Contributing

Open County Portal belongs to the counties, districts and people who use and
improve it. Contributions of every kind are welcome:

- **Reports** of bugs, accessibility barriers, and confusing wording
- **State packs** for states that don't have one, and reviews of existing ones
  by people who practice county law ([guide](docs/state-packs/writing-a-state-pack.md))
- **Payment adapters** for processors counties use ([guide](docs/contributors/payment-adapters.md))
- **Documentation** fixes, especially from administrators who followed a guide
  and got stuck
- **Code** ([developer guide](docs/contributors/README.md))
- **Translations** of resident-facing text

## How

1. **Small fixes:** open a pull request.
2. **Anything bigger:** open an issue first describing the problem and the
   change, so effort isn't wasted.
3. **Security problems:** don't open an issue; see [SECURITY.md](SECURITY.md).

Every pull request needs passing CI (tests, the conformance suite, shell
script checks, state pack validation, the image build) and a review from a
maintainer. Changes to what administrators do need documentation in the same
pull request.

## What we look for

- It helps residents, staff, or the administrators who keep it running.
- It stays accessible (WCAG 2.1 AA) and works without JavaScript.
- Changes to data can be undone, or come with a backup.
- Public data stays free and open.
- It doesn't add a dependency or a moving part without a strong reason.

## Never include

Real residents' personal information, in issues, test data or screenshots.
Use the sample data (`countyctl app demo`), which is fictional and labeled.

## Licensing of contributions

By contributing, you agree your contribution is licensed under the project's
license, the GNU Affero General Public License v3.0 or later. You keep your
copyright. Add `Signed-off-by: Your Name <email>` to commits (`git commit -s`)
to certify you have the right to contribute it, per the Developer Certificate
of Origin (https://developercertificate.org).

## Conduct

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
