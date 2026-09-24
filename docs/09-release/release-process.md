# Release Process

1. Confirm Sprint or patch scope.
2. Verify acceptance criteria.
3. Run automated and manual tests.
4. Review changed files.
5. Update changelog and release notes.
6. Confirm backup and rollback readiness.
7. Deploy from `main`.
8. Run production smoke tests.
9. Tag the release.
10. Record defects and follow-up work.


## Sprint 2 multi-tenant release evidence

Before closing Sprint 2, run both `make test-sprint2` and the complete `make test` suite, and record the exact release-candidate commit SHA plus the GitHub Actions smoke/validate results.

CI proves repository-level verification only. Tenant-domain, session, lifecycle, and platform-admin checks that require the deployed environment must be recorded separately after deployment and must not be inferred from CI.
