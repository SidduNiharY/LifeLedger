from app.notify.telegram import to_markup


def test_to_markup_keeps_callback_data():
    m = to_markup([[("Food ✓", "cat:42:Food")], [("Travel", "cat:42:Travel")]])
    assert m is not None
    assert m.inline_keyboard[1][0].callback_data == "cat:42:Travel"
    assert to_markup(None) is None
