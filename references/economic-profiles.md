# Economic profiles

The report always resolves economic context. Without a profile, or with a draft
profile, it shows the bundled Forrester TEI composite as `benchmark` evidence and
states that it is not a customer result. Only a `customer_approved` profile can
produce `projected` customer values.

## Resolution and storage

Precedence is `--economic-profile`, `JFROG_REPORT_ECONOMIC_PROFILE`, then the
per-instance default:

`~/.config/jfrog-platform-value-report/instances/<server>/economic-profile.json`

On Windows the default root is `%APPDATA%\JFrog\PlatformValueReport`. Each run
preserves `economic-profile.snapshot.json` beside its raw evidence and normalized
report. The profile may contain commercially sensitive information; the save helper
uses mode `0600` on POSIX systems.

## Modes

- `customer`: every value per unit is supplied and approved by the customer.
- `tei_assisted`: selected values per unit come from the bundled Forrester TEI
  methodology. Customer baselines, adoption coverage, realization, costs and
  approval are still required.

The deterministic formula is:

`baseline units × value per unit × adoption coverage × realization factor × (1 - risk adjustment) × scenario factor`

Every benefit model needs a unique `benefit_key`; duplicates are rejected to prevent
double counting. A non-USD TEI-assisted profile also needs an explicit USD conversion
rate, as-of date and source. Weekly JFrog findings are never automatically annualized
or treated as avoided vulnerabilities.

## Approval workflow

When a user requests customer financial modeling, collect the inputs into a draft,
show the full profile for review, and obtain explicit approval before setting
`status` to `customer_approved`. Validate and save it with:

```text
python3 scripts/save_economic_profile.py --server <server> --input <draft.json>
```

Replacing an existing profile requires `--replace`. Invalid or mismatched approved
profiles fail the report run instead of silently falling back to a benchmark.
