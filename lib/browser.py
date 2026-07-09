from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from lib.env import env_bool

CHROME_SUPPRESS_BACKGROUND_NOISE = 'CHROME_SUPPRESS_BACKGROUND_NOISE'


def build_chrome_options(extra_arguments=None):
    options = Options()
    for argument in extra_arguments or []:
        options.add_argument(argument)

    if env_bool(CHROME_SUPPRESS_BACKGROUND_NOISE, default=True):
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-sync')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

    return options


def create_chrome_driver(extra_arguments=None):
    return webdriver.Chrome(options=build_chrome_options(extra_arguments))
