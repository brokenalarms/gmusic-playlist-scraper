# coding=utf-8

from __future__ import print_function, unicode_literals
import json
import os
import sys
import re
import unicodedata
import urllib2

# pip dependencies
import argparse
from gmusicapi import Mobileclient

def parse_args(config_file_exists):
    parser = argparse.ArgumentParser()
    home_dir = os.path.expanduser("~")
    torrents_dir = os.path.join(home_dir, 'downloads', 'torrents')
    parser.add_argument("playlist", help="Google music playlist title")
    parser.add_argument("-f", "--format", default='mp3', help="optional desired format - eg 'mp3' or 'FLAC' (default is \"mp3\")")
    parser.add_argument("-d", "--dir", default=torrents_dir, help="directory for retrieved .magnet files. File can be auto-added to Deluge using the bundled 'AutoAdd' plugin. Default location is \"$HOME/Downloads\"")
    parser.add_argument("-aid", "--android_id", help="12-digit device id for login identification")
    if not config_file_exists:
        parser.add_argument("-l", "--login", help="login for Google Music", required=True)
        parser.add_argument("-p", "--password", help="password for Google Music", required=True)
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
        print('playlist not found.')
    except Exception:
        sys.exit('wrong username or password.')
    finally:
        api.logout()

# drops unicode strings like 'POLIÇA' to closest ASCII match for searching
def normalize(unicode_string):
    return unicodedata.normalize('NFKD', unicode_string).encode('ascii', 'ignore')

def replace(string, sub):
    return re.sub(r'[^a-zA-Z0-9]', sub, string)

def get_torrent_hashes(album_list, format):
    found_list = []
    not_found_list = []

    for artist_album in list(album_list):
        artist, album = artist_album
        print('Searching for {0} - {1}...'.format(artist, album))
        search_string = replace(normalize(' '.join(artist_album)), '%20')
        query = ('http://torrentproject.se/?s=' + search_string + '&out=json').lower()
        results = json.load(urllib2.urlopen(query))

        if results.pop('total_found', '0') is not '0':
            best_match = get_best_match(results, format, artist, album)
            if best_match['torrent_hash'] is not None:
                print('Found as: %s' % normalize(best_match['title']))
                found_list.append(best_match)
                save_hash_to_file(best_match, config['dir'])
            else:
                not_found_list.append(best_match)
        else: 
            print('No torrents results found.')

    if len(not_found_list) > 0:
        print('The following searches were unsuccessful:')
        for item in not_found_list:
            print('{0} - {1}: {2}'.format(item['artist'], item['album'], item['failure_message']))

    return found_list if len(found_list) > 0 else None


def get_best_match(results, format, artist, album):
    return_match = {'artist': artist, 'album': album, 'torrent_hash': None, 'failure_message': None}

    filtered_results = [match for match in results.values() if all(normalize(field).lower() in match['title'].lower() for field in [artist, album])]
    if len(results) == 0:
        return_match['failure_message'] = 'Results found but they didn\'t match the artist and album exactly.'
        return return_match

    filtered_results = sorted(filtered_results, key=lambda x: x['seeds'], reverse=True)
    if filtered_results[0] is None or filtered_results[0]['seeds'] == 0:
        return_match['failure_message'] = 'Results found, but none had seeds.'
        return return_match

    if format.lower() in ['flac', 'ape']:
        format = 'lossless'
    best_match = next((match for match in filtered_results if match['category'] == format), None)
    if best_match:
        return_match.update(best_match)
    else:
        return_match['failure_message'] = 'Results with seeds found but none in the desired file format.'
    return return_match

def save_hash_to_file(torrent_hash, dest_dir):
    dest_dir = os.path.expandvars(dest_dir)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)

    magnet_file = '{0}/{1}.magnet'.format(dest_dir, normalize(torrent_hash['title']))
    with open(magnet_file, 'w') as output_file:
        magnet_link = 'magnet:?xt=urn:btih:%s' % torrent_hash['torrent_hash']
        output_file.write(magnet_link)
    print('Results saved to %s' % magnet_file)


if __name__ == '__main__':

    config_location = os.path.join(sys.path[0], 'config.json')
    
    try:
        with open(config_location) as config_file:
            print('config.json found. reading...')
            config = json.load(config_file)
            # merge commandline args to override config args if specified
            config_args = parse_args(True)
            config.update(config_args)
            if not all(key in config for key in ['login', 'password', 'playlist']):
                raise IOError
    except IOError:
        if not os.path.isfile(config_location):
            config = parse_args(False)
        else:
            sys.exit('Invalid or incomplete config.json. Must at least contain login and password')

    album_list = get_albums_from_playlist(config)
    if album_list is not None:
        get_torrent_hashes(album_list, config['format'])