from slice_and_dice.timeline import event_times, render_timeline

SAMPLE = {
    "cou": 40,
    "dcu": 900,
    "dch": 700,
    "access_rtt": 80,
    "dns": 10,
    "coo": 50,
    "fbo": 200,
    "dco": 650,
    "fbh": 250,
    "fbu": 380,
}


def test_events_are_in_chronological_order():
    times = [moment for _, moment in event_times(SAMPLE)]
    assert times == sorted(times)


def test_proxy_events_are_offset_by_the_estimated_arrival():
    events = dict(event_times(SAMPLE))
    proxy_start = 900 - 700 + 80 // 2
    assert events["coh"] == proxy_start
    assert events["fbo"] == proxy_start + 200


def test_user_cannot_see_first_byte_before_the_origin_sends_it():
    events = dict(event_times({**SAMPLE, "fbu": 10}))
    assert events["fbu"] == events["fbo"] + 1


def test_render_timeline_draws_every_event():
    text = render_timeline(SAMPLE)
    for name in ("cou", "coh", "dns", "coo", "fbo", "fbh", "fbu", "dco", "dch", "dcu"):
        assert f" {name}" in text
    assert "->" in text


def test_render_timeline_of_an_empty_sample_does_not_divide_by_zero():
    assert render_timeline({})
