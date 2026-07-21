import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--update-baselines",
        action="store_true",
        default=False,
        help="Update visual regression test baselines",
    )


@pytest.fixture
def update_baselines(request):
    return request.config.getoption("--update-baselines")
