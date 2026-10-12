"""离线测试：不碰网络，只验纯逻辑。

跑：python -m pytest neko-plugins/neko_video/tests -q
或：python neko-plugins/neko_video/tests/test_offline.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bili import _search_queries, _similarity, strip_site_suffix
from _digest import build_digest, content_fingerprint, rhythm_hotspots
from _window import is_bilibili_live, is_bilibili_title


def test_strip_site_suffix():
    cases = {
        "机械迷城_哔哩哔哩_bilibili": "机械迷城",
        "机械迷城_哔哩哔哩_bilibili - Google Chrome": "机械迷城",
        "【官方 MV】Never Gonna Give You Up_哔哩哔哩_bilibili - Microsoft Edge": "【官方 MV】Never Gonna Give You Up",
        "某视频哔哩哔哩_bilibili": "某视频",
        "标题 - 联想浏览器": "标题",
    }
    for raw, want in cases.items():
        got = strip_site_suffix(raw)
        assert got == want, f"{raw!r} -> {got!r} != {want!r}"


def test_similarity_prefers_exact():
    q = "机械迷城"
    exact = _similarity(q, "机械迷城")
    partial = _similarity(q, "【机械迷城】解密全流程")
    unrelated = _similarity(q, "原神新版本前瞻")
    assert exact >= partial > unrelated
    # 包含关系要明显高于无关项
    assert partial > 0.7
    assert unrelated < 0.5


def test_similarity_ignores_punctuation():
    assert _similarity("abc def", "abc，def！") > 0.95


def test_rhythm_hotspots_finds_dense_point():
    msgs = (
        [{"t": 95.0 + i * 0.1, "text": "哈哈哈哈" if i % 2 else "魂游说是"}
         for i in range(6)]
        + [{"t": 10.0, "text": "开始了"}, {"t": 300.0, "text": "泪目了"}]
    )
    spots = rhythm_hotspots(msgs, top=3)
    assert spots, "应至少找到一个高点"
    top = max(spots, key=lambda s: s["count"])
    assert 95 <= top["at"] <= 100, top
    assert top["count"] == 6
    assert top["emotion"] == "笑"


def test_build_digest_is_compact():
    info = {"title": "机械迷城速通", "author": "某UP", "tname": "单机游戏",
            "duration": 213, "desc": "一个解谜游戏的速通。", "bvid": "BV1xx411c7mD"}
    # 同一 5 秒桶里 ≥3 条弹幕才构成"局部峰值"（见 rhythm_hotspots 的 min_count 门槛），
    # 否则稀疏弹幕会被判为噪音、不报"观众反应高峰"。
    dm = [{"t": 5.0 + i * 0.1, "text": t}
          for i, t in enumerate(["哈哈", "笑死", "来了", "绝了"])]
    cm = [{"text": "经典！", "like": 999}]
    digest = build_digest(info, dm, cm)
    assert "机械迷城速通" in digest
    assert "UP主 某UP" in digest
    assert "观众反应高峰" in digest
    assert "高赞评论" in digest
    assert len(digest) < 600, f"摘要太长: {len(digest)}"


def test_build_digest_handles_empty():
    info = {"title": "空视频", "bvid": "BV1xx411c7mD", "duration": 60}
    digest = build_digest(info, [], [])
    assert "空视频" in digest
    assert "弹幕稀少" in digest  # 无数据时的兜底措辞


def test_fingerprint_stable_and_distinct():
    info = {"bvid": "BV1", "title": "t"}
    dm = [{"t": 1.0, "text": "a"}]
    a1 = content_fingerprint(info, dm, [])
    a2 = content_fingerprint(info, dm, [])
    assert a1 == a2
    b = content_fingerprint(info, dm + [{"t": 2.0, "text": "b"}], [])
    assert a1 != b


def test_similarity_rejects_short_substring_trap():
    """短泛化标题偶然成为长查询子串时，绝不能得高分（否则错配到无关视频）。"""
    q = "我记录下了妹妹的最后7天...【自制伪纪录片电影】"
    trap = _similarity(q, "妹妹")          # 子串但覆盖极小
    assert trap < 0.55, f"短子串陷阱得分过高: {trap}"
    good = _similarity(q, q + "完整版")     # q 是候选的子串
    assert good > 0.8, f"真相关候选得分过低: {good}"


def test_similarity_normal_containment_still_works():
    assert _similarity("机械迷城", "【机械迷城】解密全流程") > 0.7
    assert _similarity("机械迷城", "原神前瞻") < 0.4


def test_search_queries_fallback_order():
    """多级回退查询：完整标题搜不到时，要能回退到主标题。"""
    qs = _search_queries("我记录下了妹妹的最后7天...【自制伪纪录片电影】")
    assert qs[0] == "我记录下了妹妹的最后7天...【自制伪纪录片电影】"
    assert "我记录下了妹妹的最后7天" in qs, qs
    # 主标题必须排在后备位，且不能有重复项
    assert len(qs) == len(set(qs))


def test_strip_site_suffix_lenovo():
    """联想浏览器标题（破折号后无空格）—— 实测踩过的 bug。"""
    raw = "我记录下了妹妹的最后7天...【自制伪纪录片电影】_哔哩哔哩_bilibili -联想浏览器"
    assert strip_site_suffix(raw) == "我记录下了妹妹的最后7天...【自制伪纪录片电影】"


def test_live_page_detection():
    """直播间要能识别出来（直播间没有 BV，不该去搜）。"""
    live = "假期余额不足，所以要—— - W博士与AI猫娘 - 哔哩哔哩直播，二次元弹幕直播平台 -联想浏览器"
    assert is_bilibili_title(live)
    assert is_bilibili_live(live)

    video = "机械迷城_哔哩哔哩_bilibili"
    assert is_bilibili_title(video)
    assert not is_bilibili_live(video)


def test_search_orders_cover_pubdate_first():
    """默认相关性排序会漏掉精确视频，必须优先用 pubdate —— 实测踩过的坑。"""
    import inspect

    import _bili
    src = inspect.getsource(_bili.resolve_bv_by_title)
    assert '"pubdate"' in src and '"click"' in src
    assert src.index('"pubdate"') < src.index('"click"')



def test_compose_text_kinds_differ():
    """三种时机的文案必须不同，否则她每处都说同样的话。"""
    src = open(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "__init__.py",
        encoding="utf-8",
    ).read()
    assert 'kind == "end"' in src
    assert 'kind == "hotspot"' in src
    # 收尾要提"评论"（否则等于没读高赞评论）
    s = src.index('kind == "end"')
    assert "评论" in src[s:s + 300]


def test_no_placeholders_in_compose():
    """推送文案里不能出现角色名占位符 —— 实测可见气泡不会替换它们。"""
    src = open(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "__init__.py",
        encoding="utf-8",
    ).read()
    start = src.index("def _compose_text")
    body = src[start:start + 1800]
    assert "{master}" not in body, "文案里还有 {master} 占位符"
    assert "{lanlan_name}" not in body, "文案里还有 {lanlan_name} 占位符"

def test_hotspot_fires_when_playback_reaches_it():
    """播到峰值那一刻才开口 —— 事件驱动，不是定时。"""
    from _schedule import due_hotspot

    spots = [{"at": 20.0}, {"at": 95.0}, {"at": 200.0}]
    fired = set()
    # 才播到 10 秒：一个都还没到
    assert due_hotspot(spots, fired, elapsed=10, now=100, last_push_at=0) is None
    # 播到 25 秒：该报 20 秒那个
    got = due_hotspot(spots, fired, elapsed=25, now=100, last_push_at=0)
    assert got and got["at"] == 20.0
    fired.add(20.0)
    # 播到 100 秒：跳过 95 之前已处理的，报 95
    got = due_hotspot(spots, fired, elapsed=100, now=100, last_push_at=0)
    assert got and got["at"] == 95.0


def test_hotspot_never_repeats():
    """同一个高光点只吐一次（硬去重）。"""
    from _schedule import due_hotspot

    spots = [{"at": 30.0}]
    assert due_hotspot(spots, {30.0}, elapsed=40, now=100, last_push_at=0) is None


def test_hotspot_respects_min_gap():
    """刚说完话就别马上再说 —— 唯一的时间约束只是"别吞上一句"。"""
    from _schedule import due_hotspot

    spots = [{"at": 10.0}, {"at": 12.0}]
    # 5 秒前刚开过口，最短间隔 18 秒 → 先别说
    assert due_hotspot(spots, set(), elapsed=20, now=100, last_push_at=95, min_gap=18) is None
    # 过了 18 秒 → 可以说了
    assert due_hotspot(spots, set(), elapsed=20, now=120, last_push_at=95, min_gap=18) is not None


def test_stale_hotspots_not_backreported():
    """用户拖进度条跳过的高光点不回头补报。"""
    from _schedule import stale_hotspots

    spots = [{"at": 10.0}, {"at": 480.0}]
    # 看到 500 秒时：10 秒处早就过去了（490 > 90，过期）
    #                480 秒处刚过去（20 <= 90，还在宽限内，可以补）
    stale = stale_hotspots(spots, set(), elapsed=500, grace=90)
    assert 10.0 in stale, "早过去的高光点应标记为已处理"
    assert 480.0 not in stale, "仍在宽限内的不该丢"


def test_sorted_hotspots_by_time():
    from _schedule import sorted_hotspots

    out = sorted_hotspots([{"at": 90}, {"at": 10}, {"at": 50}])
    assert [h["at"] for h in out] == [10, 50, 90]


def test_rhythm_hotspots_prefers_local_peaks():
    """相邻两个高密度桶，只报最高的那个（同一波弹幕别报两次）。"""
    from _digest import rhythm_hotspots

    # 100 秒处 8 条，105 秒处 3 条，其余零星
    msgs = [{"t": 100.0 + i * 0.1, "text": f"笑死{i}"} for i in range(8)]
    msgs += [{"t": 105.0 + i * 0.1, "text": f"哈哈{i}"} for i in range(3)]
    msgs += [{"t": 5.0, "text": "开始"}, {"t": 300.0, "text": "结尾"}]
    spots = rhythm_hotspots(msgs, top=5)
    ats = [s["at"] for s in spots]
    assert 100 in ats
    assert 105 not in ats, "相邻低峰不该单独上报"
    top = max(spots, key=lambda s: s["count"])
    assert top["at"] == 100 and top["count"] == 8
    assert top["samples"], "高光点要带上多条弹幕供她取材"


def test_build_intro_and_hotspot_text():
    from _digest import build_hotspot_text, build_intro_text

    info = {"title": "高糖VS戒糖14天", "author": "亿点点", "duration": 702, "bvid": "BV1x"}
    dm = [{"t": 200.0 + i, "text": t} for i, t in enumerate(["赛掌柜口音", "笑容消失术", "太好笑了"])]
    intro = build_intro_text(info, dm, [{"text": "标题该严谨点", "like": 517}])
    assert "高糖VS戒糖14天" in intro
    assert "观众反应高峰" in intro     # 告诉她之后会在哪些点提醒
    assert "高赞评论" in intro

    hs = {"at_label": "3:20", "emotion": "笑", "count": 12, "sample": "笑容消失术", "samples": ["太好笑了"]}
    txt = build_hotspot_text(info, hs)
    assert "3:20" in txt and "笑容消失术" in txt


def test_estimate_position_extrapolates_while_playing():
    """播放中系统只报一次位置 —— 必须靠 upd + 倍速外推（实测行为）。"""
    from _playback import estimate_position

    frame = {"status": "Playing", "rate": 1.0, "pos": 3.53, "upd": 1789000000.0, "end": 708.0}
    # 过了 20 秒仍在播放：3.53 + 20*1
    assert abs(estimate_position(frame, 1789000020.0) - 23.53) < 1e-6
    # 倍速 2x：同样的 20 秒墙钟，位置前进 40 秒
    frame2 = dict(frame, rate=2.0)
    assert abs(estimate_position(frame2, 1789000020.0) - 43.53) < 1e-6


def test_estimate_position_paused_is_exact():
    """暂停时 pos 就是准确位置，绝不能再外推。"""
    from _playback import estimate_position

    frame = {"status": "Paused", "rate": 0.0, "pos": 547.43, "upd": 1789000000.0, "end": 708.0}
    assert estimate_position(frame, 1789999999.0) == 547.43


def test_estimate_position_rejects_bad_data():
    from _playback import estimate_position

    assert estimate_position(None, 0) is None
    assert estimate_position({"status": "Playing", "pos": -1}, 0) is None
    # upd 不是合理的 Unix 秒 → 不臆造外推，返回 pos 本身
    assert estimate_position({"status": "Playing", "pos": 12.0, "upd": 0, "rate": 1}, 1e9) == 12.0


def test_progress_ratio():
    from _playback import progress_ratio

    frame = {"status": "Paused", "rate": 0.0, "pos": 50.0, "upd": 0, "end": 200.0}
    assert progress_ratio(frame, 0) == 0.25
    assert progress_ratio({"status": "Playing", "pos": 10, "end": 0}, 0) is None


def test_pick_bilibili_frame_skips_noise():
    """多路媒体会话里只挑 B站视频；音乐、直播间都要排除。"""
    from _playback import pick_bilibili_frame

    rows = [
        {"app": "cloudmusic.exe", "status": "Playing", "title": "某首歌 - 网易云音乐"},
        {"app": "SLBrowser", "status": "Paused", "title": "某主播 - 哔哩哔哩直播，二次元弹幕直播平台"},
        {"app": "SLBrowser", "status": "Playing", "title": "机械迷城_哔哩哔哩_bilibili"},
    ]
    got = pick_bilibili_frame(rows)
    assert got is not None and got["app"] == "SLBrowser" and got["status"] == "Playing"
    assert "机械迷城" in got["title"]
    # 只有直播间 → 视为没有可用会话
    assert pick_bilibili_frame([rows[1]]) is None
    # 只有音乐 → None
    assert pick_bilibili_frame([rows[0]]) is None
    assert pick_bilibili_frame([]) is None


def test_pick_bilibili_frame_prefers_playing_over_paused():
    from _playback import pick_bilibili_frame

    rows = [
        {"app": "a", "status": "Paused", "title": "旧视频_哔哩哔哩_bilibili"},
        {"app": "b", "status": "Playing", "title": "新视频_哔哩哔哩_bilibili"},
    ]
    assert pick_bilibili_frame(rows)["app"] == "b"


def test_title_matches_guards_wrong_session():
    """别的标签页/别的视频的会话，绝不能把位置错用到当前视频上。"""
    from _playback import title_matches

    assert title_matches("机械迷城_哔哩哔哩_bilibili", "机械迷城_哔哩哔哩_bilibili -联想浏览器")
    assert title_matches(
        "【官方 MV】Never Gonna Give You Up_哔哩哔哩_bilibili",
        "【官方 MV】Never Gonna Give You Up_哔哩哔哩_bilibili",
    )
    assert not title_matches("原神新版本前瞻_哔哩哔哩_bilibili", "机械迷城_哔哩哔哩_bilibili")
    assert not title_matches("", "机械迷城_哔哩哔哩_bilibili")


def test_smtc_script_is_self_contained():
    """SMTC 读取脚本必须自带 WinRT 访问逻辑，且用 EncodedCommand 传（不落盘）。"""
    import _smtc

    src = _smtc._PS_SCRIPT_TEMPLATE
    assert "GlobalSystemMediaTransportControlsSessionManager" in src
    assert "GetTimelineProperties" in src
    assert "ConvertTo-Json" in src


def test_smtc_reader_degrades_when_unavailable():
    """非 Windows / 未启动时，latest() 必须安全返回 None（插件靠它降级）。"""
    import _smtc

    r = _smtc.SmtcReader()
    assert isinstance(r.available(), bool)
    assert r.latest() is None      # 未 start：必须是 None，不是异常


def test_plugin_wires_media_position_with_fallback():
    """插件必须：优先真实播放位置，读不到时退回墙钟估算（源码级契约）。"""
    src = open(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "__init__.py",
        encoding="utf-8",
    ).read()
    assert "use_media_session" in src
    assert "_playback_now" in src
    # 降级路径必须存在：媒体位置拿不到时，从**最近一次真实观测**续推（last_pos
    # + 墙钟），再没有就退回"检测到视频起算"的墙钟估算（见 _process_title）。
    assert "last_pos" in src
    assert "last_pos_at" in src


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"  FAIL {name}: {e}")
    print("=" * 40)
    print("全部通过" if not fails else f"{fails} 个失败")
    sys.exit(1 if fails else 0)
