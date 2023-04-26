import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="frankAllSkyCam",                 # This is the name of the package
    version="3.0.",                         # The initial release version
    author="Francesco Sferlazza",           # Full name of the author
    description="AllSkyCam Package",
    long_description=long_description,      # Long description read from the the readme file
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),    # List of all python modules to be installed
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],                                      # Information to filter the project on PyPi website
    python_requires='>=3.9',                # Minimum version requirement of the package
    py_modules=["__main__.py"],             # Name of the python package
    package_dir={'':'allskycam/src'},       # Directory of the source code of the package
    install_requires=["pytz", "numpy"]                     # Install other dependencies if any
)

