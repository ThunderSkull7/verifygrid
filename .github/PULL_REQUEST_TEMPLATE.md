## Summary of Changes

A clear, concise summary of the changes proposed in this Pull Request.

- Relates to Issue: #
- Component(s) affected: [e.g. `aggregation_engine`, `migrations/env.py`, `ReconciliationWizard.tsx`]

---

## Type of Change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Performance optimization
- [ ] Breaking change (fix or feature causing existing behavior to change)
- [ ] Documentation update
- [ ] Security / Governance hardening

---

## Verification & Testing

Please describe the tests executed to verify these changes:

- [ ] Backend offline test suite passes (`pytest backend/tests -m "not postgres"`)
- [ ] Target guard test suite passes (`pytest backend/tests/test_migration_env_guard.py`)
- [ ] Financial aggregation regression suite passes (`pytest backend/tests/test_financial_aggregation_batches_a_d.py`)
- [ ] Frontend full test suite passes (`npm test` in `frontend/`)
- [ ] Frontend type check and build pass (`npm run build` in `frontend/`)
- [ ] No remote database credentials, secrets, or internal hostnames committed

---

## Security & Operational Checklist

- [ ] Database transactions maintain explicit caller ownership (no unhandled rollbacks in guards)
- [ ] Financial calculations explicitly distinguish valid zero ($0.00) from corrupt/missing amounts
- [ ] Public registration role defaults to `MAKER` without privilege elevation paths
- [ ] Cryptographic audit hashes remain chained and verifiable
