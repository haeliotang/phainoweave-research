# Ethics review records

One record per reviewed change to the capability surface. A review is required when a change materially raises precision or lowers the cost of the capability: a new modality, a verifier library that tightens regions, a model that improves point accuracy, or a new data source that enables person-level inference.

This directory is empty until the first such change is proposed. The gate is defined in [ethics and privacy](../ethics-and-privacy.md) and [ADR 0005](../../decisions/0005-privacy-and-dual-use.md).

## Required record

```
YYYY-MM-DD-<slug>.md
```

Content: the change, the precision/cost delta it creates, the misuse cases considered, the red-team case that was run, the mitigation adopted, the decision (allow / gate / decline), the reviewers, and the conditions under which the decision must be revisited.
