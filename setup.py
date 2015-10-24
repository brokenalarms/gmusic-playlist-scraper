from setuptools import setup

setup(
	name='gmusic-playlist-scraper',
	version='0.1',
	url='https://github.com/breakingco/gmusic-playlist-scraper',
	author='Daniel Lawrence',
	author_email='brokenalarms@gmail.com',
	licence='MIT',
	install_requires=[
	'argparse',
	'gmusicapi',
	'requests']
	)