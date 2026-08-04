from webutils.fancy.faust import (
    apply_color_gradient,
    apply_color_gradient_custom,
    process_dlg_text,
)


def test_gradient_two_chars():
    assert apply_color_gradient_custom("你好", "#ff0000", "#ffffff", 2.0) == (
        "<color=#ff0000>你</color><color=#ffffff>好</color>"
    )


def test_gradient_preserves_mid_tag():
    assert apply_color_gradient_custom(
        "a<color=#00ff00>b</color>c", "#ff0000", "#ffffff", 2.0
    ) == (
        "<color=#ff0000>a</color>"
        "<color=#00ff00><color=#ffbfbf>b</color></color>"
        "<color=#ffffff>c</color>"
    )


def test_gradient_keeps_special_chars_raw():
    assert apply_color_gradient_custom("a\nb\tc", "#ff0000", "#ffffff", 2.0) == (
        "<color=#ff0000>a</color>\n<color=#ffbfbf>b</color>\t<color=#ffffff>c</color>"
    )


def test_gradient_single_char_uses_start_color():
    assert apply_color_gradient_custom("x", "#ff0000", "#ffffff", 2.0) == (
        "<color=#ff0000>x</color>"
    )


def test_gradient_empty_text_returns_empty():
    assert apply_color_gradient_custom("", "#ff0000", "#ffffff", 2.0) == ""


def test_gradient_only_tags_wraps_whole_text():
    assert apply_color_gradient_custom("<color=#ff0000></color>", "#ff0000", "#ffffff", 2.0) == (
        "<color=#ff0000><color=#ff0000></color></color>"
    )


def test_gradient_angle_bracket_sequence_treated_as_tag():
    assert apply_color_gradient_custom("< 3 >", "#ff0000", "#ffffff", 2.0) == (
        "<color=#ff0000>< 3 ></color>"
    )


def test_gradient_nested_tags():
    assert apply_color_gradient_custom(
        "<b><color=#ff0000>ab</color></b>", "#ff0000", "#ffffff", 2.0
    ) == (
        "<b><color=#ff0000><color=#ff0000>a</color><color=#ffffff>b</color></color></b>"
    )


def test_gradient_rate_0p3():
    assert apply_color_gradient("abc", "#2020ED", 0.3) == (
        "<color=#2020ed>a</color><color=#4949f0>b</color><color=#ffffff>c</color>"
    )


def test_process_dlg_text_gradients_first_color_match():
    assert process_dlg_text("前<color=#ff0000>中</color>后", 0.4) == (
        "前<color=#ff0000>中</color>后"
    )


def test_process_dlg_text_without_color_unchanged():
    assert process_dlg_text("没有颜色", 0.4) == "没有颜色"


def test_process_dlg_text_multiline_color():
    assert process_dlg_text("第一行<color=#00ff00>跨\n行</color>结尾", 0.5) == (
        "第一行<color=#00ff00>跨</color>\n<color=#ffffff>行</color>结尾"
    )


def test_process_dlg_text_only_first_color_processed():
    assert process_dlg_text(
        "<color=#111111>一</color><color=#222222>二</color>", 0.5
    ) == "<color=#111111>一</color><color=#222222>二</color>"
