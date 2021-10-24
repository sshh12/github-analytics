import setuptools


with open("README.md", "r") as fh:
    long_description = fh.read()


setuptools.setup(
    name="github_analytics",
    version="0.0.0",
    author="Shrivu Shankar",
    author_email="shrivu1122@gmail.com",
    description="Info about GitHub usage.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sshh12/github-analytics",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
