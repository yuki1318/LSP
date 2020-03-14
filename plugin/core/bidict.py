from .typing import Any, Set


class BidirectionalDictionary(dict):
    """
    A dictionary-like object that maintains a set filled with its values for fast lookup of the values.
    Consequently, the values inserted into this dictionary are required to be hashable, too.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._inverse = set(self.values())  # type: Set[Any]

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self._inverse.add(value)

    def __delitem__(self, key: Any) -> None:
        value = super().get(key)
        self._inverse.discard(value)
        super().__delitem__(key)

    def has_value(self, value: Any) -> bool:
        """
        Is this value in the dictionary?
        """
        return value in self._inverse

    def pop(self, key: Any, default: Any = None) -> Any:
        if key in self:
            value = super().pop(key)
            self._inverse.remove(value)
            return value
        return default
