from __future__ import print_function
import json
import os
import sys

# pip dependencies
import argparse

def parse_args():
    pass

if __name__ == '__main__':

    config_location = os.path.join(sys.path[0], 'config.json')
    try:
        with open(config_location) as config_file:
            print('config.json found. reading...')
            config = json.load(config_file)
    except IOError as e:
        if not os.path.isfile(config_location):
            parse_args()
        else:
            print('invalid config.json')

