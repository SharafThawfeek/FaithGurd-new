import random

import pytest

from faithguard.stats import (
    clopper_pearson_upper,
    cluster_bootstrap,
    cohen_kappa,
    fixed_sequence,
    hb_pvalue,
    hb_zero_error_budget,
    selective_risk_pvalue,
    zero_error_budget,
)


def test_zero_error_budgets_match_the_plan():
    assert zero_error_budget(0.10) == 29
    assert zero_error_budget(0.05) == 59
    assert hb_zero_error_budget(0.10) >= 29  # the linearised certificate is a little more demanding


def test_hb_pvalue_behaves():
    assert hb_pvalue(0.2, 100, 0.1) == 1.0  # observed risk above alpha: no evidence
    assert hb_pvalue(0.0, 200, 0.1) < 1e-6
    assert hb_pvalue(0.05, 400, 0.1) < hb_pvalue(0.05, 100, 0.1)


def test_selective_risk_certificate_on_simulated_data_has_valid_coverage():
    """With true conditional risk above alpha, the certificate should almost never pass."""
    rng = random.Random(1)
    alpha, delta, false_certs = 0.10, 0.05, 0
    for _ in range(300):
        sent = [rng.random() < 0.7 for _ in range(400)]
        unsafe = [s and rng.random() < 0.13 for s in sent]  # true risk among sent = 0.13 > alpha
        if selective_risk_pvalue(unsafe, sent, alpha) <= delta:
            false_certs += 1
    assert false_certs / 300 <= delta


def test_selective_risk_certifies_a_safe_policy():
    rng = random.Random(2)
    sent = [rng.random() < 0.7 for _ in range(1000)]
    unsafe = [s and rng.random() < 0.02 for s in sent]
    assert selective_risk_pvalue(unsafe, sent, 0.10) < 0.05


def test_fixed_sequence_stops_at_first_failure():
    assert fixed_sequence([0.001, 0.01, 0.2, 0.001], 0.05) == [0, 1]


def test_clopper_pearson():
    assert clopper_pearson_upper(0, 29) == pytest.approx(0.0983, abs=1e-3)


def test_cohen_kappa_textbook_example():
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)
    assert cohen_kappa(a, a) == 1.0


def test_cluster_bootstrap_is_wider_than_naive_when_clusters_differ():
    records = [(g, v) for g in range(10) for v in [g % 2] * 20]  # each issuer all 0 or all 1
    mean = lambda rs: sum(v for _, v in rs) / len(rs)
    est, lo, hi = cluster_bootstrap(records, lambda r: r[0], mean, n_boot=500)
    naive_est, naive_lo, naive_hi = cluster_bootstrap(records, lambda r: id(r), mean, n_boot=500)
    assert est == pytest.approx(0.5)
    assert (hi - lo) > (naive_hi - naive_lo)
