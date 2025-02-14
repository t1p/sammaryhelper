from setuptools import setup, find_packages

setup(
    name="Sammaryhelper",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "telethon",
        "openai",
        "pytz",
        "python-socks",
        "asyncio"
    ],
    author="TIP"
)
