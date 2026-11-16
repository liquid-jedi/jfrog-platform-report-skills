# Metric contract

Every metric contains `id`, `label`, `classification`, `value`, `unit`, `sources`,
`formula`, `confidence`, and `data_gaps`.

Projected metrics also contain `projection` with baseline, assumptions,
applicability, adoption coverage, realization factor, value per unit, conservative,
expected, and optimistic scenarios, confidence level, and data gaps.

Financial totals use decimal arithmetic and configured currency. Benefit allocation uses
unique `benefit_keys`; duplicate keys are a validation failure. NPV discounts annual net
cash flows with a configured rate. ROI is unavailable when total cost is zero. Payback is
zero when cost is zero, unavailable when benefit is zero, otherwise annual cost divided
by annual benefit in years.
