from fastgpt_exporter.batching import chunk_items


def test_empty_list():
    assert list(chunk_items([])) == []


def test_exact_multiple_of_max_count():
    items = [{"q": str(i)} for i in range(400)]
    batches = list(chunk_items(items, max_count=200))
    assert [len(b) for b in batches] == [200, 200]


def test_remainder_batch():
    items = [{"q": str(i)} for i in range(450)]
    batches = list(chunk_items(items, max_count=200))
    assert [len(b) for b in batches] == [200, 200, 50]


def test_single_item_under_limits():
    items = [{"q": "hello"}]
    assert list(chunk_items(items)) == [[{"q": "hello"}]]


def test_byte_cap_splits_before_count_cap():
    big_item = {"q": "x" * 1000}
    items = [big_item] * 20
    batches = list(chunk_items(items, max_count=200, max_bytes=5000))
    assert len(batches) > 1
    assert sum(len(b) for b in batches) == 20


def test_oversized_single_item_still_yielded_alone():
    huge_item = {"q": "x" * 20000}
    batches = list(chunk_items([huge_item], max_count=200, max_bytes=100))
    assert batches == [[huge_item]]
