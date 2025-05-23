from setuptools import setup, find_packages

setup(
    name='jc-CSV',
    version='0.1.0',  # Or your desired version
    author='Jeff Clough', # Replace with your name
    author_email='jeff@cloughcottage.com', # Replace with your email
    description='A tool and API for manipulating CSV data.',
    long_description=open('README.md').read(), #Optional, and create the README.md file
    long_description_content_type='text/markdown', #Optional
    url='https://github.com/jc-handy/CSV',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            # Our CLI script is __main__.py, which contains a main() function.
            'csvtool = CSV.csvtool:main',
        ],
    },
    install_requires=[
        'jc-debug',
        'jc-handy-helpers',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',  # Or your desired status
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License', # Or your desired license
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12', # Or your supported Python versions
        'Programming Language :: Python :: 3.13',
    ],
    python_requires='>=3.11', #Or whatever minimum version you require.
)
