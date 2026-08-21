from webmedia_dl.names import (
    CLI_NAME,
    DISPLAY_NAME,
    PACKAGE_NAME,
    PERSONAL_ALIAS,
    SWIFT_MODULE_PREFIX,
)


def test_canonical_names() -> None:
    assert DISPLAY_NAME == "WebMedia DL"
    assert CLI_NAME == "webmedia-dl"
    assert PACKAGE_NAME == "webmedia_dl"
    assert SWIFT_MODULE_PREFIX == "WebMediaDL"
    assert PERSONAL_ALIAS == "wmdl"
    assert PERSONAL_ALIAS != CLI_NAME
