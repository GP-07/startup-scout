import pytest

from startups.page_metrics import PageMetrics, is_probable_spa_shell, measure_page

CONTENT_PAGE = (
    "<html><body><nav><a href='/'>Home</a><a href='/pricing'>Pricing</a>"
    "<a href='/about'>About</a></nav><main><h1>Acme</h1>"
    f"<p>{'Robots that move pallets around warehouses. ' * 10}</p></main></body></html>"
)
REACT_SHELL = (
    "<html><head><script src='/main.js'></script></head>"
    "<body><noscript>You need to enable JavaScript to run this app.</noscript>"
    "<div id='root'></div></body></html>"
)


def test_measures_visible_text_links_and_app_root():
    metrics = measure_page(CONTENT_PAGE)

    assert metrics.link_count == 3
    assert metrics.text_length > 300
    assert metrics.has_app_root is False


def test_script_and_noscript_text_does_not_count_as_visible():
    metrics = measure_page(REACT_SHELL)

    assert metrics.text_length == 0
    assert metrics.link_count == 0
    assert metrics.has_app_root is True


@pytest.mark.parametrize("root_id", ["root", "app", "__next", "__nuxt", "___gatsby"])
def test_framework_mount_points_are_app_roots(root_id):
    assert measure_page(f"<body><div id='{root_id}'>Hi</div></body>").has_app_root is True


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        (PageMetrics(text_length=0, link_count=0, has_app_root=True), True),
        (PageMetrics(text_length=50, link_count=10, has_app_root=False), True),
        (PageMetrics(text_length=800, link_count=1, has_app_root=True), True),
        (PageMetrics(text_length=800, link_count=1, has_app_root=False), False),
        (PageMetrics(text_length=800, link_count=12, has_app_root=True), False),
    ],
)
def test_probable_spa_shell_has_little_text_or_an_app_root_with_almost_no_links(metrics, expected):
    assert is_probable_spa_shell(metrics) is expected
