"""Unit and Integration tests for EmpiricalPaperSuite."""

import pytest

from app.tests.empirical_paper_suite import EmpiricalPaperSuite


@pytest.mark.asyncio
async def test_empirical_paper_suite_execution() -> None:
    from app.domain.bloom_filter import bloom_filter_service
    from app.infra.dataset_sync_job import SEED_DISPOSABLE_DOMAINS

    bloom_filter_service.load_domains(SEED_DISPOSABLE_DOMAINS, version="v1.0.0-seed")

    suite = EmpiricalPaperSuite()
    report = await suite.run_full_suite()

    assert "bloom_filter_theoretical_vs_empirical" in report
    bloom = report["bloom_filter_theoretical_vs_empirical"]
    assert bloom["capacity_N"] == 500000
    assert bloom["bound_satisfied"] is True

    assert "pipeline_latency_and_throughput" in report
    latency = report["pipeline_latency_and_throughput"]
    assert latency["total_requests"] == 200
    assert latency["throughput_requests_per_second"] > 0

    assert "privacy_by_design_audit" in report
    privacy = report["privacy_by_design_audit"]
    assert privacy["privacy_by_design_compliant"] is True
    assert privacy["local_part_discarded_pre_lookup"] is True

    # Verify snapshot save & load contract
    assert bloom_filter_service.save_snapshot("/tmp/test_bloom_snapshot.bin") is True  # noqa: S108
    assert bloom_filter_service.load_snapshot("/tmp/test_bloom_snapshot.bin") is not None  # noqa: S108

    # Verify LaTeX summary export contract
    suite.export_latex_summary("/tmp/test_empirical_results.tex")  # noqa: S108
    import os

    assert os.path.exists("/tmp/test_empirical_results.tex") is True  # noqa: S108
