from slice_and_dice.policy_script import bandwidth_mbps, burst_size, render_policy_scripts


def test_burst_size_rounds_up_with_headroom():
    assert burst_size(5960) == 6200
    assert burst_size(0) == 3000


def test_bandwidth_is_rounded_to_five_mbps_steps():
    assert bandwidth_mbps(9_000_000) == 15
    assert bandwidth_mbps(0) == 5


def test_render_policy_scripts():
    scripts = render_policy_scripts(
        [{"scope": {"network": "HSPA-Plus"}, "max_burst": 5960, "max_bandwidth": 9_000_000}],
        base_scope={"cid": "42", "geo": "US", "os": "ios"},
        match_fields=["cid", "geo", "network"],
    )
    assert len(scripts) == 1
    lines = scripts[0].strip().splitlines()
    assert lines[0] == "rm cid42-US-HSPA+"
    assert "set cid42-US-HSPA+ from network HSPA+" in lines
    assert "set cid42-US-HSPA+ then strategies mb_6200_15 server max-burst 6200" in lines
    assert "set cid42-US-HSPA+ then strategies mb_7200_15 server max-burst 7200" in lines
    assert "os" not in scripts[0]


def test_policies_without_matching_fields_are_skipped():
    scripts = render_policy_scripts(
        [{"scope": {"os": "ios"}, "max_burst": 1}], base_scope={}, match_fields=["geo"]
    )
    assert scripts == []
