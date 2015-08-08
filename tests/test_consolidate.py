
from mhi import _consolidate

def test_flatten():
    assert _consolidate([1,3,5,7,9]) == '1,3,5,7,9'
    assert _consolidate([1,2,3,5,7,9]) == '1-3,5,7,9'
    assert _consolidate([1,3,4,5,7,9]) == '1,3-5,7,9'
    assert _consolidate([1,3,5,6,7,9]) == '1,3,5-7,9'
    assert _consolidate([1,3,5,7,8,9]) == '1,3,5,7-9'

