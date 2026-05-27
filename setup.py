from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [
        line.strip()
        for line in fh
        if line.strip() and not line.strip().startswith("#")
    ]

setup(
    name="xauusd-scalper",
    version="0.1.0",
    description="XAUUSD AI scalping bot with MT5 integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="",
    url="",
    packages=find_packages(exclude=("tests",)),
    include_package_data=True,
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "xauusd-scalper=main:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
)

