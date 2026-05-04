"""
Dominian Setup Script
"""

try:
    from setuptools import setup, find_packages
except ImportError:
    print("Error: setuptools is required. Please install with: pip install setuptools")
    exit(1)

setup(
    name="dominian",
    version="1.0.9",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "dominian": ["*.py"],
    },
    entry_points={
        "console_scripts": [
            "dominian=main_new:main",
            "dominian-mcp=server:main",
        ],
    },
    python_requires=">=3.10",
    install_requires=[
        "mcp>=1.0.0",
    ],
    extras_require={
        "community": [
            "networkx>=3.0",
            "python-louvain>=0.16",
        ],
        "tree-sitter": [
            "tree-sitter>=0.20.0",
            "tree-sitter-python>=0.20.0",
            "tree-sitter-javascript>=0.20.0",
            "tree-sitter-typescript>=0.20.0",
            "tree-sitter-java>=0.20.0",
            "tree-sitter-go>=0.20.0",
            "tree-sitter-rust>=0.20.0",
        ],
        "all": [
            "dominian[community,tree-sitter]",
        ],
    },
)
