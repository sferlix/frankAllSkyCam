from distutils.core import setup

setup(
  name = 'frankAllSkyCam',
  packages = ['frankAllSkyCam'],
  version = '10.2',
  license='MIT',
  description = 'AllSkyCamera with Raspberry Pi and Pi HQ Camera ',
  author = 'Francesco Sferlazza',
  author_email = 'sferlazza@gmail.com',
  url = 'https://github.com/sferlix/frankAllSkyCam',
  download_url = 'https://github.com/sferlix/frankAllSkyCam/archive/refs/tags/10.2.tar.gz',
  keywords = ['AllSkyCamera', 'Astronomy', 'AllSky'],
  package_data={'': ['moon.png','compass.png','logo.png','index.html', 'sqmexp.csv', 'jupiter.png', 'saturn.png', 'mars.png', 'venus.png','config.txt']},
  include_package_data=True,
  install_requires=[
          'pytz',
          'numpy',
          'pandas',
          'ephem',
          'wand'
      ],
  classifiers=[
    'Development Status :: 4 - Beta',
    'Intended Audience :: Developers',
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Programming Language :: Python :: 3.9',
  ],
)



