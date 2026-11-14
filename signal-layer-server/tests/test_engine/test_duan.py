from __future__ import annotations

from app.engine.chan.bi import Bi
from app.engine.chan.zhongshu import build_duans


SF0_ENDPOINTS = [
    6494, 5948, 6960, 6168, 6442, 6160, 6578, 5940, 6084, 5468,
    5760, 5014, 5468, 5308, 6298, 5588, 6124, 5590, 5736, 5438,
    5856, 5308, 5626, 5448, 5616, 5362, 5926, 5496, 5762, 5452,
    6196, 5616, 6086, 5804, 6008, 5584, 5854, 5722, 6624,
]

# 000004_sz 日线 2024-05 ~ 2026-06 的笔端点（首笔起点 + 每笔终点）
SZ000004_ENDPOINTS = [
    12.38, 8.32, 11.20, 9.04, 11.77, 9.31, 13.25, 10.21, 12.50, 10.87,
    24.81, 17.58, 20.59, 16.63, 19.26, 17.92, 20.84, 12.10, 13.90, 10.35,
    14.59, 7.80, 10.31, 7.19, 10.70, 8.40, 9.44, 8.56, 8.97, 8.52,
    9.26, 8.78, 11.88, 9.95, 11.83, 10.03, 13.98, 12.02, 13.52, 10.35,
    12.59, 9.91, 11.41, 10.38, 13.20, 5.07, 6.40, 3.02, 3.82, 0.25,
]


def make_bis(endpoints: list[float]) -> list[Bi]:
    return [
        Bi(
            index=index,
            direction="down" if index % 2 == 0 else "up",
            fx_a=None,
            fx_b=None,
            bars=[],
            start_time=index,
            end_time=index + 1,
            start_price=endpoints[index],
            end_price=endpoints[index + 1],
            high=max(endpoints[index:index + 2]),
            low=min(endpoints[index:index + 2]),
            power=abs(endpoints[index + 1] - endpoints[index]),
        )
        for index in range(len(endpoints) - 1)
    ]


def test_sz000004_duans_follow_trend_swings() -> None:
    duans = build_duans(make_bis(SZ000004_ENDPOINTS))

    assert [
        (item.direction, item.bi_indices[0], item.bi_indices[-1], item.end_price)
        for item in duans
    ] == [
        ("up", 1, 15, 20.84),
        ("down", 16, 22, 7.19),
        ("up", 23, 35, 13.98),
        ("down", 36, 48, 0.25),
    ]
    assert duans[-1].fenxing_type is None


def test_sz000004_first_duan_keeps_internal_high() -> None:
    duans = build_duans(make_bis(SZ000004_ENDPOINTS))

    assert duans[0].bi_indices[0] == 1
    assert duans[0].start_price == 8.32
    assert duans[0].high == 24.81
    assert duans[0].low == 8.32


def test_sf0_base_segments_keep_reversals() -> None:
    duans = build_duans(make_bis(SF0_ENDPOINTS))

    assert [
        (item.direction, item.bi_indices[0], item.bi_indices[-1], item.end_price)
        for item in duans
    ] == [
        ("down", 0, 10, 5014),
        ("up", 11, 13, 6298),
        ("down", 14, 18, 5438),
        ("up", 19, 25, 5926),
        ("down", 26, 28, 5452),
        ("up", 29, 37, 6624),
    ]
    assert duans[-1].fenxing_type is None


def test_all_confirmed_duans_share_boundaries_without_gaps() -> None:
    for endpoints in (SF0_ENDPOINTS, SZ000004_ENDPOINTS):
        duans = build_duans(make_bis(endpoints))
        assert len(duans) >= 2
        for previous, current in zip(duans, duans[1:]):
            assert previous.end_time == current.start_time
            assert previous.end_price == current.start_price
            assert previous.bi_indices[-1] + 1 == current.bi_indices[0]
            assert len(previous.bi_indices) >= 3
            assert len(current.bi_indices) >= 3

def test_duan_feature_elements_stay_inside_segment() -> None:
    for endpoints in (SF0_ENDPOINTS, SZ000004_ENDPOINTS):
        duans = build_duans(make_bis(endpoints))
        for duan in duans:
            allowed = set(duan.bi_indices)
            for item in duan.feat_elements or []:
                assert item["bi"] in allowed
            for item in duan.merged_feat or []:
                assert item["bi"] in allowed


def test_sz000004_feature_elements_do_not_leak_past_segment_end() -> None:
    duans = build_duans(make_bis(SZ000004_ENDPOINTS))

    assert [item["bi"] for item in duans[0].feat_elements or []] == [2, 4, 6, 8, 10, 12, 14]
    assert [item["bi"] for item in duans[1].feat_elements or []] == [17, 19, 21]
