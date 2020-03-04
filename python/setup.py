import subprocess
import sys
from setuptools.command.develop import develop
import setuptools
from sys import platform

class DevelopWrapper(develop):
  """Compiles the otm-python-api so that pyotm can
  call on the OTM api."""

  def run(self):
    # Run this first so the develop stops in case
    # these fail otherwise the Python package is
    # successfully developed
    self._compile_otm_python_api()
    develop.run(self)

  def _compile_otm_python_api(self):
    try:
        if platform == "linux" or platform == "linux2" or platform == "darwin":
            subprocess.call('mvn package -f javacnct/pom.xml -DskipTests'.split(' '))
        elif platform == "win32":
            subprocess.call('mvn package -f javacnct/pom.xml -DskipTests'.split(' '), shell=True)
    except Exception as err:
        print("Please install maven")
        sys.exit(1)

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="otm",
    version="0.1",
    author="Gabriel Gomes",
    author_email="gomes@berkeley.edu",
    description="Python package for OTM",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ggomes/otm-tools",
    packages=setuptools.find_packages(),
    # classifiers=[
    #     "Programming Language :: Python :: 3",
    #     "License :: OSI Approved :: MIT License",
    #     "Operating System :: OS Independent",
    # ],
    cmdclass={'develop': DevelopWrapper}
)
