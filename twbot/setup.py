from setuptools import setup, find_packages

setup(
    name='twtrbot',
    version='0.2',
    packages=['twtrbot'],
    url='https://github.com/emilybarbour/twtrbot',
    license='MIT',
    author='Emily B.',
    author_email='eb3604@gmail.com',
    description='Gently stalks twitter user(s)',
    install_requires=[
        "Pillow",
        "pytz",
        'requests',
        'requests_oauthlib',
        'selenium'
    ],
)
