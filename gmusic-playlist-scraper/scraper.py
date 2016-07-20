# coding=utf-8

from __future__ import print_function, unicode_literals
from builtins import input
import json
import os
import sys
import re
import unicodedata
import urllib2

# pip dependencies
import argparse
from gmusicapi import Mobileclient
from gmusicapi.exceptions import NotLoggedIn

def parse_args():
    parser = argparse.ArgumentParser()
    home_dir = os.path.expanduser("~")
    torrents_dir = os.path.join(home_dir, 'downloads', 'torrents')
    parser.add_argument("playlist", nargs='?', help="Google music playlist title")
    parser.add_argument("-f", "--format", default='mp3', help="optional desired format - eg 'mp3' or 'FLAC' (default is \"mp3\")")
    parser.add_argument("-d", "--dir", default=torrents_dir, help="directory for retrieved .magnet files. File can be auto-added to Deluge using the bundled 'AutoAdd' plugin. Default location is \"$HOME/downloads/torrents\"")
    parser.add_argument("-aid", "--android_id", help="12-digit device id for login identification")
    parser.add_argument("-l", "--login", help="login for Google Music")
    parser.add_argument("-p", "--password", help="password for Google Music")
    # return dictionary format for merging commandline and config options
    return vars(parser.parse_args())

def get_albums_from_playlist(config):
    login, password, playlist_name, android_id = map(config.get, ('login', 'password', 'playlist', 'android_id'))
    api = Mobileclient()
    if not android_id:
        android_id = Mobileclient.FROM_MAC_ADDRESS 
    try:
        api.login(login, password, android_id)
        all_playlists = api.get_all_user_playlist_contents()
        matched_playlist = next(playlist for playlist in all_playlists if playlist['name'].lower() == playlist_name.lower())
        album_list = {(entry['track']['albumArtist'], entry['track']['album'])
              for entry in matched_playlist['tracks'] if 'track' in entry}
        return album_list
    except StopIteration:
        sys.exit('playlist not found.')
    except NotLoggedIn:
        sys.exit('wrong username or password.')
    finally:
        api.logout()

# drops unicode strings like 'POLIÇA' to closest ASCII match for searching
def normalize(unicode_string):
    return unicodedata.normalize('NFKD', unicode_string).encode('ascii', 'ignore')

def get_torrent_hashes(album_list, file_format, save_dir):
    found_list = []
    not_found_list = []

    for artist_album in list(album_list):
        artist, album = artist_album
        print('\nSEARCHING: "{0} - {1}"'.format(artist, album))
        search_string = urllib2.quote(normalize(' '.join(artist_album)).lower(), safe='')
        query = ('http://torrentproject.se/?s=' + search_string + '&out=json')
        results = json.load(urllib2.urlopen(query))

        best_match = get_best_match(results, file_format, artist, album)
        if best_match['torrent_hash'] is not None:
            print('FOUND: {0}'.format(normalize(best_match['title'])))
            found_list.append(best_match)
            save_hash_to_file(best_match, save_dir)
        else:
            print('Torrent not found or potential alternatives rejected.')
            not_found_list.append(best_match)

    print('\nSUCCESSFUL:')
    for item in found_list:
        print('{0} - {1}'.format(item['artist'], item['album']))

    if len(not_found_list) > 0:
        print('\nUNSUCCESSFUL:')
        for item in not_found_list:
            print('{0} - {1}:'.format(item['artist'], item['album']))
            print('\t %s' % item['failure_message'])

    return found_list if len(found_list) > 0 else None

def suggest_alternative(best_match, filtered_results, error_msg):
    print('ERROR: {0}'.format(error_msg));
    print('Would you like to take any of the following alternatives?')
    for idx, result in enumerate(filtered_results):
        print('{0}: {1} (format: {2})'.format(idx + 1, result['title'], result['category']))
    answer = input('Choose alternative (0 for none):')

    while not answer.isdigit() or int(answer) > len(filtered_results): 
        answer = input('Invalid choice. Choose alternative (0 for none):')
    choice = int(answer)
    if choice == 0: 
        best_match['failure_message'] = error_msg
        return best_match

    best_match.update(filtered_results[choice - 1])
    return best_match
 

def get_best_match(results, file_format, artist, album):
    best_match = {'artist': artist, 'album': album, 'torrent_hash': None, 'failure_message': None}

    if results.pop('total_found') == '0':
        best_match['failure_message'] = 'No torrent results found.'
        return best_match

    all_results = results.values()
    filtered_results = [match for match in all_results if all(normalize(field).lower() in match['title'].lower() for field in [artist, album])]
    if len(filtered_results) == 0:
        error_msg = 'Results found for either artist or album but they didn\'t match both exactly.'
        best_match = suggest_alternative(best_match, all_results, error_msg)
        return best_match

    filtered_results = sorted(filtered_results, key=lambda x: x['seeds'], reverse=True)
    if filtered_results[0]['seeds'] == 0:
        best_match['failure_message'] = 'Results found, but none had seeds.'
        return best_match

    if file_format.lower() in ['flac', 'ape']:
        file_format = 'lossless'
    try:
        found_match = next((match for match in filtered_results if match['category'] == file_format))
        best_match.update(found_match)
    except StopIteration:
        error_msg = 'Results with seeds were found but none in the desired format.'
        best_match = suggest_alternative(best_match, filtered_results, error_msg)

    return best_match

def save_hash_to_file(torrent_hash, dest_dir):
    dest_dir = os.path.expandvars(dest_dir)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    magnet_filename = normalize(torrent_hash['title']) + os.extsep + 'magnet'
    magnet_filepath = os.path.join(dest_dir, magnet_filename)
    with open(magnet_filepath, 'w') as output_file:
        magnet_link = 'magnet:?xt=urn:btih:%s' % torrent_hash['torrent_hash']
        output_file.write(magnet_link)
    print('SAVED: magnet file to "%s".' % magnet_filepath)


def main():
    config_location = os.path.join(sys.path[0], 'config.json')
    if os.path.isfile(config_location):
        print('config.json found. reading...')
        with open(config_location) as config_file:
            config = json.load(config_file)
            # merge any extra present commandline args to override config.json args
            config_args = parse_args()
            commandline_args = {key: config_args[key] for key in config_args if config_args[key] is not None}
            config.update(commandline_args)
    else:
       config = parse_args()
    
    if not all(key in config for key in ['login', 'password', 'playlist']):
        error_msg = 'Invalid or incomplete combination of args in config.json and commandline. Must at least contain login, password, and playlist.'
        sys.exit(error_msg)
            
    album_list = get_albums_from_playlist(config)
    if album_list is not None:
        print('\nSaving found magnet links to {0}..'.format(config['dir']))
        get_torrent_hashes(album_list, config['format'], config['dir'])

if __name__ == '__main__':
    sys.exit(main())