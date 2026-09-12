"""上游缓存锁定位(Cache.py 受控改造)的回归测试。

锁定语义:locked 条目强制命中——post_src 变化、retry_failed、retran_key、
校对模式都不再送回翻译;写缓存(post_save 快照/append)透传 locked 字段。
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from GalTransl.Cache import get_transCache_from_json, save_transCache_to_json  # noqa: E402
from GalTransl.CSentense import CSentense, CTransList  # noqa: E402


def make_chain(specs: list[dict]) -> CTransList:
    """按 (speaker, pre_src) 列表构造带 prev/next 链的翻译列表。"""
    trans_list = CTransList()
    prev = None
    for i, spec in enumerate(specs):
        tran = CSentense(
            pre_src=spec["pre_src"], speaker=spec.get("speaker", ""), index=i
        )
        tran.prev_tran = prev
        if prev is not None:
            prev.next_tran = tran
        trans_list.append(tran)
        prev = tran
    return trans_list


def write_cache(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def cache_key_for(entries: list[dict], i: int) -> str:
    """与上游三联键同构:prev+now+next 的 name+pre_src。"""
    def part(e):
        return f'{e.get("name", "")}{e.get("pre_src", "")}'

    now = part(entries[i])
    prv = part(entries[i - 1]) if i > 0 else "None"
    nxt = part(entries[i + 1]) if i < len(entries) - 1 else "None"
    return prv + now + nxt


@pytest.fixture
def cache_pair(tmp_path):
    """两条缓存条目:A 正常,B 人工锁定。返回 (cache_path, entries)。"""
    entries = [
        {
            "index": 0,
            "name": "Alice",
            "pre_src": "こんにちは。",
            "post_src": "こんにちは。",
            "pre_dst": "你好。",
            # 上游 _build_cache_obj 总会写 proofread_dst(可为空串);
            # 若缺失该字段,no_proofread 判定为 False 会跳过 post_src 检查
            "proofread_dst": "",
        },
        {
            "index": 1,
            "name": "Alice",
            "pre_src": "これはペンです。",
            "post_src": "これはペンです。",
            "pre_dst": "钢笔人工定稿。",
            "proofread_dst": "",
            "locked": True,
        },
    ]
    cache_path = tmp_path / "test_cache.json"
    write_cache(cache_path, entries)
    return cache_path, entries


def test_locked_survives_post_src_change(cache_pair):
    """锁定条目:post_src 变化仍命中(未锁条目同场景应 unhit)。"""
    cache_path, entries = cache_pair
    trans_list = make_chain(
        [
            {"speaker": "Alice", "pre_src": "こんにちは。"},
            {"speaker": "Alice", "pre_src": "これはペンです。"},
        ]
    )
    # 模拟 post_src 被润色改变
    trans_list[0].post_src = "こんにちは!(改)"
    trans_list[1].post_src = "これはペンなんだ。(改)"

    hit, unhit = asyncio.run(get_transCache_from_json(trans_list, str(cache_path)))

    assert trans_list[0] in unhit, "未锁条目 post_src 变化必须 unhit"
    assert trans_list[1] in hit, "锁定条目 post_src 变化也必须强制命中"
    assert trans_list[1].pre_dst == "钢笔人工定稿。"


def test_locked_flag_roundtrip_via_tran(cache_pair):
    """命中后 tran.locked 回填;post_save 快照写回时 locked 字段保留。"""
    cache_path, entries = cache_pair
    trans_list = make_chain(
        [
            {"speaker": "Alice", "pre_src": "こんにちは。"},
            {"speaker": "Alice", "pre_src": "これはペンです。"},
        ]
    )
    asyncio.run(get_transCache_from_json(trans_list, str(cache_path)))
    assert trans_list[1].locked is True
    assert trans_list[0].locked is False

    asyncio.run(save_transCache_to_json(trans_list, str(cache_path), post_save=True))
    saved = json.loads(cache_path.read_text(encoding="utf-8"))
    by_index = {e["index"]: e for e in saved}
    assert by_index[1].get("locked") is True, "post_save 全量快照不得丢 locked"
    assert "locked" not in by_index[0]


def test_locked_skips_retran_key(cache_pair):
    """锁定条目即使命中重译关键字也不重翻。"""
    cache_path, _ = cache_pair
    trans_list = make_chain(
        [
            {"speaker": "Alice", "pre_src": "こんにちは。"},
            {"speaker": "Alice", "pre_src": "これはペンです。"},
        ]
    )
    hit, unhit = asyncio.run(
        get_transCache_from_json(
            trans_list, str(cache_path), retran_key="ペン"
        )
    )
    assert trans_list[1] in hit, "锁定条目不参与 retran_key 重翻"


def test_unlocked_still_retranslates_on_retran_key(cache_pair):
    """对照:未锁条目命中重译关键字仍会重翻。"""
    cache_path, _ = cache_pair
    trans_list = make_chain(
        [
            {"speaker": "Alice", "pre_src": "こんにちは。"},
            {"speaker": "Alice", "pre_src": "これはペンです。"},
        ]
    )
    hit, unhit = asyncio.run(
        get_transCache_from_json(
            trans_list, str(cache_path), retran_key="こんにちは"
        )
    )
    assert trans_list[0] in unhit


def test_locked_skips_proofread_queue(cache_pair):
    """校对模式:锁定条目不进未校对队列。"""
    cache_path, _ = cache_pair
    trans_list = make_chain(
        [
            {"speaker": "Alice", "pre_src": "こんにちは。"},
            {"speaker": "Alice", "pre_src": "これはペンです。"},
        ]
    )
    hit, unhit = asyncio.run(
        get_transCache_from_json(trans_list, str(cache_path), proofread=True)
    )
    assert trans_list[1] in hit, "锁定条目视为终稿,不进校对队列"
    assert trans_list[0] in unhit, "未锁且未校对条目正常进入校对队列"
