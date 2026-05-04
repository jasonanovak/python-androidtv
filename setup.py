"""setup.py file for the androidtv_wifi package."""

from setuptools import setup

with open("README.rst") as f:
    readme = f.read()

setup(
    name="androidtv-wifi",
    version="0.1.1",
    description="Fork of androidtv (python-androidtv) that uses adb-shell-wifi to add modern ADB Wi-Fi (TLS) pairing support.",
    long_description=readme,
    long_description_content_type="text/x-rst",
    keywords=["adb", "android", "androidtv", "firetv", "wifi", "tls"],
    url="https://github.com/jasonanovak/python-androidtv",
    license="MIT",
    author="Jason Novak",
    author_email="jason@nvkmail.com",
    packages=["androidtv_wifi", "androidtv_wifi.adb_manager", "androidtv_wifi.basetv", "androidtv_wifi.androidtv", "androidtv_wifi.firetv"],
    install_requires=[
        "adb-shell-wifi==0.5.0",
        "pure-python-adb>=0.3.0.dev0",
    ],
    extras_require={
        "async": ["aiofiles>=0.4.0", "async_timeout>=3.0.0"],
        "usb": ["adb-shell-wifi[usb]==0.5.0"],
        "wifi": [
            "adb-shell-wifi[wifi]==0.5.0",
            "aiofiles>=0.4.0",
            "async_timeout>=3.0.0",
        ],
    },
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 2",
    ],
    test_suite="tests",
)
