from __future__ import annotations

from app.engine.chan.bi import Bi
from app.engine.chan.zhongshu import build_duans


SF0_ENDPOINTS = [
    6494, 5948, 6960, 6168, 6442, 6160, 6578, 5940, 6084, 5468,
    5760, 5014, 5468, 5308, 6298, 5588, 6124, 5590, 5736, 5438,
    5856, 5308, 5626, 5448, 5616, 5362, 5926, 5496, 5762, 5452,
    6196, 5616, 6086, 5804, 6008, 5584, 5854, 5722, 6624,
]


def make_sf0_bis() -> list[Bi]:
    return [
        Bi(
            index=index,
            direction="down" if index % 2 == 0 else "up",
            fx_a=None,
            fx_b=None,
            bars=[],
            start_time=index,
            end_time=index + 1,
            start_price=SF0_ENDPOINTS[index],
            end_price=SF0_ENDPOINTS[index + 1],
            high=max(SF0_ENDPOINTS[index:index + 2]),
            low=min(SF0_ENDPOINTS[index:index + 2]),
            power=abs(SF0_ENDPOINTS[index + 1] - SF0_ENDPOINTS[index]),
        )
        for index in range(len(SF0_ENDPOINTS) - 1)
    ]


def test_sf0_third_duan_endpoint_moves_to_point_21() -> None:
    duans = build_duans(make_sf0_bis())

    assert len(duans) >= 4
    assert duans[2].end_time == 21
    assert duans[2].end_price == 5308
    assert duans[2].bi_indices[-1] == 20
    assert duans[3].start_time == 21
    assert duans[3].start_price == 5308
    assert duans[3].bi_indices[0] == 21


def test_all_confirmed_duans_share_boundaries_without_gaps() -> None:
    duans = build_duans(make_sf0_bis())

    for previous, current in zip(duans, duans[1:]):
        assert previous.end_time == current.start_time
        assert previous.end_price == current.start_price
